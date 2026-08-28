#!/usr/bin/env python3
"""
inventory.py — Production-grade Ansible Inventory & Vault Manager
=================================================================
Unified CLI utility for dynamic inventory generation, Ansible Vault
password management, validation, backup/restore, and host lifecycle
operations for enterprise/HPC environments.

Architecture: Option 1 (unified application)
  - Single entry point, modular internal design
  - Dataclass-driven host model
  - Strict secret isolation: passwords never appear in stdout/logs/JSON
  - Atomic writes + file locking for concurrent-safe operations

Usage:
    inventory.py --list
    inventory.py --host <hostname>
    inventory.py --validate
    inventory.py --sync-vault
    inventory.py --add-host
    inventory.py --delete-host <hostname>
    inventory.py --update-host <hostname>
    inventory.py --backup
    inventory.py --restore <backup_file>
    inventory.py --export <output_file>
    inventory.py --import <input_file>

Author: Generated for OpenCHAI / HPC production environment
Python: 3.11+
"""

from __future__ import annotations

import argparse
import fcntl
import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(os.environ.get("ANSIBLE_INVENTORY_BASE", Path(__file__).parent))

CONFIG = {
    "inventory_file": BASE_DIR / "inventory" / "inventory_def.txt",
    "vault_file": BASE_DIR / "inventory" / "group_vars" / "all" / "vault.yml",
    "vault_pass_file": BASE_DIR / ".vault_pass",
    "host_vars_dir": BASE_DIR / "inventory" / "host_vars",
    "group_vars_dir": BASE_DIR / "inventory" / "group_vars",
    "backup_dir": BASE_DIR / "backups",
    "log_dir": BASE_DIR / "logs",
    "log_file": BASE_DIR / "logs" / "inventory.log",
    "lock_file": BASE_DIR / ".inventory.lock",
    "default_ssh_port": 22,
    "log_max_bytes": 10 * 1024 * 1024,   # 10 MB
    "log_backup_count": 5,
}


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------

class InventoryError(Exception):
    """Base exception for all inventory errors."""

class ParseError(InventoryError):
    """Raised when the inventory file cannot be parsed."""

class ValidationError(InventoryError):
    """Raised when inventory data fails validation."""

class VaultError(InventoryError):
    """Raised when vault operations fail."""

class LockError(InventoryError):
    """Raised when the inventory lock cannot be acquired."""

class BackupError(InventoryError):
    """Raised when backup/restore operations fail."""

class HostNotFoundError(InventoryError):
    """Raised when a requested host does not exist."""


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def setup_logging(log_file: Path, debug: bool = False) -> logging.Logger:
    """Configure dual-sink logging: rotating file + console."""
    log_file.parent.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO
    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    date_fmt = "%Y-%m-%dT%H:%M:%S"

    logger = logging.getLogger("inventory")
    logger.setLevel(level)

    if logger.handlers:
        return logger  # already configured (re-import guard)

    # Rotating file handler
    fh = RotatingFileHandler(
        log_file,
        maxBytes=CONFIG["log_max_bytes"],
        backupCount=CONFIG["log_backup_count"],
        encoding="utf-8",
    )
    fh.setFormatter(logging.Formatter(fmt, date_fmt))
    fh.setLevel(level)

    # Console handler — INFO and above only (never DEBUG secrets)
    ch = logging.StreamHandler(sys.stderr)
    ch.setFormatter(logging.Formatter(fmt, date_fmt))
    ch.setLevel(logging.INFO)

    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


log = logging.getLogger("inventory")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class HostRecord:
    """Represents one inventory host. Password is NEVER stored on this object."""
    node: str           # Ansible inventory hostname
    ip: str             # IP address
    user: str           # SSH login user
    group: str          # Ansible group
    hostname: str       # Linux hostname
    ssh_port: int       # SSH port
    # password intentionally excluded

    def to_hostvars(self) -> dict:
        """Return safe host variables dict (no secrets)."""
        return {
            "ansible_host": self.ip,
            "ansible_user": self.user,
            "ansible_port": self.ssh_port,
            "hostname": self.hostname,
            "group": self.group,
        }

    def to_inventory_line(self) -> str:
        """Serialize back to inventory file format (6 fields, no password)."""
        return f"{self.node} {self.ip} {self.user} {self.group} {self.hostname} {self.ssh_port}"


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

_VALID_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-\.]+$")


def validate_ip(ip: str) -> str:
    """Validate and return an IPv4 address string, raising ValidationError on failure."""
    try:
        addr = ipaddress.IPv4Address(ip)
        return str(addr)
    except ipaddress.AddressValueError:
        raise ValidationError(f"Invalid IPv4 address: {ip!r}")


def validate_port(port_str: str) -> int:
    """Parse and range-check an SSH port."""
    try:
        port = int(port_str)
    except ValueError:
        raise ValidationError(f"SSH port must be an integer, got: {port_str!r}")
    if not (1 <= port <= 65535):
        raise ValidationError(f"SSH port out of range (1-65535): {port}")
    return port


def validate_name(name: str, field: str) -> str:
    """Ensure a hostname/node/group name contains only safe characters."""
    if not name:
        raise ValidationError(f"Empty value for field '{field}'")
    if not _VALID_NAME_RE.match(name):
        raise ValidationError(
            f"Field '{field}' contains invalid characters: {name!r}. "
            "Only alphanumerics, hyphens, underscores, and dots are allowed."
        )
    return name


# ---------------------------------------------------------------------------
# File locking
# ---------------------------------------------------------------------------

class FileLock:
    """Context manager for exclusive file-based locking."""

    def __init__(self, lock_path: Path, timeout: float = 30.0):
        self._path = lock_path
        self._timeout = timeout
        self._fd: Optional[int] = None

    def __enter__(self) -> "FileLock":
        deadline = time.monotonic() + self._timeout
        self._path.touch(exist_ok=True)
        self._fd = os.open(self._path, os.O_RDWR)
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                log.debug("Lock acquired: %s", self._path)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(self._fd)
                    raise LockError(
                        f"Could not acquire lock on {self._path} within {self._timeout}s. "
                        "Another process may be modifying the inventory."
                    )
                time.sleep(0.2)

    def __exit__(self, *_) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            log.debug("Lock released: %s", self._path)


# ---------------------------------------------------------------------------
# Atomic write helper
# ---------------------------------------------------------------------------

def atomic_write(path: Path, content: str, mode: int = 0o644) -> None:
    """Write *content* to *path* atomically via a temp file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp, mode)
        os.replace(tmp, path)      # POSIX: rename is atomic
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Inventory parser
# ---------------------------------------------------------------------------

def parse_inventory_file(
    path: Path,
) -> tuple[list[HostRecord], list[str]]:
    """
    Parse a 6-field inventory file (node ip user group hostname ssh_port).

    Returns (records, warnings).  Raises ParseError on fatal errors.
    NOTE: The 7-field format (with password) is intentionally rejected here;
    the password field must never be in the inventory file at rest.
    """
    if not path.exists():
        raise ParseError(f"Inventory file not found: {path}")

    records: list[HostRecord] = []
    warnings: list[str] = []
    seen_nodes: dict[str, int] = {}
    seen_ips: dict[str, int] = {}

    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()

            # Skip blanks and comments
            if not line or line.startswith("#"):
                continue

            parts = line.split()

            # Reject 7-field lines — password should never rest in inventory
            if len(parts) == 7:
                raise ParseError(
                    f"Line {lineno}: password field detected in inventory file. "
                    "The inventory file must contain exactly 6 fields. "
                    "Remove the password column and use --sync-vault to store secrets."
                )

            if len(parts) != 6:
                warnings.append(
                    f"Line {lineno}: expected 6 fields, got {len(parts)} — skipped: {line!r}"
                )
                continue

            node_raw, ip_raw, user_raw, group_raw, hostname_raw, port_raw = parts

            # Field-level validation
            try:
                node = validate_name(node_raw, "node")
                ip = validate_ip(ip_raw)
                user = validate_name(user_raw, "user")
                group = validate_name(group_raw, "group")
                hostname = validate_name(hostname_raw, "hostname")
                port = validate_port(port_raw)
            except ValidationError as exc:
                warnings.append(f"Line {lineno}: {exc} — skipped")
                continue

            # Duplicate detection
            if node in seen_nodes:
                warnings.append(
                    f"Line {lineno}: duplicate node name '{node}' "
                    f"(first seen on line {seen_nodes[node]}) — skipped"
                )
                continue
            if ip in seen_ips:
                warnings.append(
                    f"Line {lineno}: duplicate IP '{ip}' for node '{node}' "
                    f"(first seen on line {seen_ips[ip]}) — skipped"
                )
                continue

            seen_nodes[node] = lineno
            seen_ips[ip] = lineno
            records.append(HostRecord(node, ip, user, group, hostname, port))

    return records, warnings


# ---------------------------------------------------------------------------
# Inventory generator (--list / --host)
# ---------------------------------------------------------------------------

def build_inventory_json(records: list[HostRecord]) -> dict:
    """Construct the Ansible dynamic inventory JSON structure."""
    groups: dict[str, dict] = {}
    hostvars: dict[str, dict] = {}

    for r in records:
        groups.setdefault(r.group, {"hosts": [], "vars": {}})
        groups[r.group]["hosts"].append(r.node)
        hostvars[r.node] = r.to_hostvars()

    return {"_meta": {"hostvars": hostvars}, **groups}


# ---------------------------------------------------------------------------
# Vault manager
# ---------------------------------------------------------------------------

class VaultManager:
    """
    Manages an Ansible Vault-encrypted YAML file containing host passwords.

    Vault file structure (encrypted at rest):
        vault_passwords:
          master01: <password>
          compute001: <password>
    """

    def __init__(
        self,
        vault_file: Path,
        vault_pass_file: Path,
        host_vars_dir: Path,
    ):
        self.vault_file = vault_file
        self.vault_pass_file = vault_pass_file
        self.host_vars_dir = host_vars_dir

        if not vault_pass_file.exists():
            raise VaultError(
                f"Vault password file not found: {vault_pass_file}. "
                "Create it with your vault password (chmod 600)."
            )
        # Safety check: vault pass file permissions
        stat = vault_pass_file.stat()
        if stat.st_mode & 0o077:
            log.warning(
                "Vault password file %s has loose permissions (%o). "
                "Recommended: chmod 600.",
                vault_pass_file,
                stat.st_mode & 0o777,
            )

    def _run_vault(self, args: list[str], input_data: Optional[str] = None) -> subprocess.CompletedProcess:
        """Run ansible-vault with the configured password file. Raises VaultError on failure."""
        cmd = [
            "ansible-vault",
            *args,
            #"--vault-password-file", str(self.vault_pass_file),
        ]
        log.debug("Running ansible-vault (args redacted for security)")
        try:
            result = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except FileNotFoundError:
            raise VaultError(
                "ansible-vault not found. Install Ansible: pip install ansible-core"
            )
        except subprocess.TimeoutExpired:
            raise VaultError("ansible-vault timed out after 30 seconds")

        if result.returncode != 0:
            # Scrub any potential secret echo from stderr before logging
            safe_stderr = re.sub(r"(?i)(password|secret|pass)\s*[:=]\s*\S+", "[REDACTED]", result.stderr)
            raise VaultError(f"ansible-vault failed: {safe_stderr.strip()}")

        return result

    def decrypt_vault(self) -> str:
        """Decrypt and return vault file contents as plaintext YAML string."""
        if not self.vault_file.exists():
            return "vault_passwords: {}\n"
        result = self._run_vault(["decrypt", "--output=-", str(self.vault_file)])
        return result.stdout

    def _parse_vault_yaml(self, plaintext: str) -> dict[str, str]:
        """
        Parse the decrypted vault YAML into {node: password} dict.
        Uses simple line-by-line parsing to avoid a PyYAML dependency
        and to prevent accidental secret serialization via yaml.dump.
        """
        passwords: dict[str, str] = {}
        in_block = False
        for line in plaintext.splitlines():
            stripped = line.strip()
            if stripped == "vault_passwords:":
                in_block = True
                continue
            if in_block:
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and not line.startswith("\t"):
                    break  # end of block
                if ":" in stripped:
                    key, _, val = stripped.partition(":")
                    passwords[key.strip()] = val.strip().strip("\"'")
        return passwords

    def _build_vault_yaml(self, passwords: dict[str, str]) -> str:
        """Serialize {node: password} to YAML string. Passwords stay in-process only."""
        lines = ["vault_passwords:"]
        for node in sorted(passwords):
            # Wrap value in double quotes to handle special characters
            escaped = passwords[node].replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'  {node}: "{escaped}"')
        return "\n".join(lines) + "\n"

    def _encrypt_and_write(self, plaintext: str) -> None:
        """Encrypt plaintext YAML and write atomically to vault file."""
        self.vault_file.parent.mkdir(parents=True, exist_ok=True)

        # Write plaintext to a temp file, encrypt in-place, then atomic rename
        fd, tmp = tempfile.mkstemp(prefix=".vault_tmp_", dir=self.vault_file.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(plaintext)
            os.chmod(tmp, 0o600)
            self._run_vault(["encrypt", tmp])
            os.replace(tmp, self.vault_file)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        finally:
            # Overwrite plaintext variable in memory (best-effort)
            plaintext = "\x00" * len(plaintext)  # noqa: F841

    def sync(self, records: list[HostRecord], passwords: dict[str, str]) -> int:
        """
        Sync vault: add/update entries for every host in *records* that has
        a corresponding password in *passwords*.  Returns number of entries updated.
        """
        current = {}
        try:
            current = self._parse_vault_yaml(self.decrypt_vault())
        except VaultError:
            log.warning("Could not read existing vault — will create fresh.")

        updated = 0
        for r in records:
            if r.node in passwords:
                if current.get(r.node) != passwords[r.node]:
                    current[r.node] = passwords[r.node]
                    updated += 1

        self._encrypt_and_write(self._build_vault_yaml(current))

        # Also write per-host host_vars stubs (no passwords — those live in vault)
        for r in records:
            self._write_host_vars_stub(r)

        log.info("Vault sync complete. %d password(s) added/updated.", updated)
        return updated

    def rotate(self, node: str, new_password: str) -> None:
        """Replace the vault password for a single host."""
        current = self._parse_vault_yaml(self.decrypt_vault())
        if node not in current:
            raise VaultError(f"Host '{node}' not found in vault.")
        current[node] = new_password
        self._encrypt_and_write(self._build_vault_yaml(current))
        log.info("Password rotated for host '%s'.", node)

    def delete(self, node: str) -> None:
        """Remove a host's password from the vault."""
        current = self._parse_vault_yaml(self.decrypt_vault())
        if node not in current:
            log.warning("Host '%s' not found in vault — nothing to delete.", node)
            return
        del current[node]
        self._encrypt_and_write(self._build_vault_yaml(current))
        log.info("Vault entry deleted for host '%s'.", node)

    def list_nodes(self) -> list[str]:
        """Return sorted list of nodes registered in the vault."""
        current = self._parse_vault_yaml(self.decrypt_vault())
        return sorted(current.keys())

    def _write_host_vars_stub(self, record: HostRecord) -> None:
        """
        Write a host_vars YAML stub that references vault variables.
        Passwords are NOT embedded here — they come from the encrypted vault.
        """
        self.host_vars_dir.mkdir(parents=True, exist_ok=True)
        path = self.host_vars_dir / f"{record.node}.yml"
        content = (
            "---\n"
            f"# Host vars for {record.node} — auto-generated, do not edit manually\n"
            f"ansible_user: {record.user}\n"
            f"ansible_host: {record.ip}\n"
            f"ansible_port: {record.ssh_port}\n"
            "ansible_password: \"{{ vault_passwords[inventory_hostname] }}\"\n"
            "ansible_become_pass: \"{{ vault_passwords[inventory_hostname] }}\"\n"
        )
        atomic_write(path, content, mode=0o640)
        log.debug("host_vars stub written: %s", path)


# ---------------------------------------------------------------------------
# Host lifecycle operations
# ---------------------------------------------------------------------------

class InventoryManager:
    """High-level operations on the inventory file and vault."""

    def __init__(self, config: dict):
        self.inv_file: Path = config["inventory_file"]
        self.vault_pass_file: Path = config["vault_pass_file"]
        self.vault_file: Path = config["vault_file"]
        self.host_vars_dir: Path = config["host_vars_dir"]
        self.backup_dir: Path = config["backup_dir"]
        self.lock_file: Path = config["lock_file"]

        self._vault: Optional[VaultManager] = None

    @property
    def vault(self) -> VaultManager:
        if self._vault is None:
            self._vault = VaultManager(
                self.vault_file, self.vault_pass_file, self.host_vars_dir
            )
        return self._vault

    def load(self) -> tuple[list[HostRecord], list[str]]:
        """Parse inventory file, returning (records, warnings)."""
        return parse_inventory_file(self.inv_file)

    def save(self, records: list[HostRecord]) -> None:
        """Atomically persist records to the inventory file."""
        lines = ["# Ansible Inventory Definition — auto-managed by inventory.py"]
        lines.append(f"# Updated: {datetime.now().isoformat()}")
        lines.append("# Format: node ip user group hostname ssh_port")
        lines.append("")
        for r in records:
            lines.append(r.to_inventory_line())
        lines.append("")
        atomic_write(self.inv_file, "\n".join(lines), mode=0o640)
        log.info("Inventory saved: %d host(s) → %s", len(records), self.inv_file)

    # ------------------------------------------------------------------
    # Host CRUD
    # ------------------------------------------------------------------

    def add_host(
        self,
        node: str, ip: str, user: str, group: str,
        hostname: str, ssh_port: int, password: str,
    ) -> None:
        """Add a new host to inventory and vault atomically."""
        with FileLock(self.lock_file):
            records, _ = self.load()
            existing_nodes = {r.node for r in records}
            existing_ips = {r.ip for r in records}

            if node in existing_nodes:
                raise ValidationError(f"Host '{node}' already exists. Use --update-host.")
            ip_val = validate_ip(ip)
            if ip_val in existing_ips:
                raise ValidationError(f"IP {ip_val} already assigned to another host.")

            new_record = HostRecord(node, ip_val, user, group, hostname, ssh_port)
            records.append(new_record)
            self.save(records)
            self.vault.sync(records, {node: password})
        log.info("Host '%s' added successfully.", node)

    def delete_host(self, node: str) -> None:
        """Remove a host from inventory and vault."""
        with FileLock(self.lock_file):
            records, _ = self.load()
            before = len(records)
            records = [r for r in records if r.node != node]
            if len(records) == before:
                raise HostNotFoundError(f"Host '{node}' not found in inventory.")
            self.save(records)
            self.vault.delete(node)

            # Remove host_vars stub
            stub = self.host_vars_dir / f"{node}.yml"
            if stub.exists():
                stub.unlink()
                log.debug("Removed host_vars stub: %s", stub)

        log.info("Host '%s' deleted.", node)

    def update_host(
        self,
        node: str,
        *,
        ip: Optional[str] = None,
        user: Optional[str] = None,
        group: Optional[str] = None,
        hostname: Optional[str] = None,
        ssh_port: Optional[int] = None,
        password: Optional[str] = None,
    ) -> None:
        """Update one or more fields for an existing host."""
        with FileLock(self.lock_file):
            records, _ = self.load()
            target = next((r for r in records if r.node == node), None)
            if target is None:
                raise HostNotFoundError(f"Host '{node}' not found in inventory.")

            if ip is not None:
                ip_val = validate_ip(ip)
                used_ips = {r.ip for r in records if r.node != node}
                if ip_val in used_ips:
                    raise ValidationError(f"IP {ip_val} is already assigned to another host.")
                target.ip = ip_val
            if user is not None:
                target.user = validate_name(user, "user")
            if group is not None:
                target.group = validate_name(group, "group")
            if hostname is not None:
                target.hostname = validate_name(hostname, "hostname")
            if ssh_port is not None:
                target.ssh_port = validate_port(str(ssh_port))

            self.save(records)

            if password is not None:
                self.vault.sync(records, {node: password})
            else:
                # Re-sync host_vars stub with updated fields
                self.vault._write_host_vars_stub(target)

        log.info("Host '%s' updated.", node)

    # ------------------------------------------------------------------
    # Vault sync
    # ------------------------------------------------------------------

    def sync_vault(self, passwords: dict[str, str]) -> int:
        """Sync all provided passwords into the vault."""
        with FileLock(self.lock_file):
            records, warnings = self.load()
            for w in warnings:
                log.warning(w)
            n = self.vault.sync(records, passwords)
        return n

    # ------------------------------------------------------------------
    # Backup / Restore
    # ------------------------------------------------------------------

    def backup(self) -> Path:
        """Create a timestamped backup of the inventory and vault."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{ts}"
        backup_path.mkdir()

        files_to_backup = [self.inv_file, self.vault_file]
        host_vars = list(self.host_vars_dir.glob("*.yml")) if self.host_vars_dir.exists() else []

        backed_up = []
        for src in files_to_backup + host_vars:
            if src.exists():
                rel = src.relative_to(BASE_DIR)
                dest = backup_path / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                backed_up.append(str(rel))

        manifest = {
            "timestamp": ts,
            "files": backed_up,
            "host_count": sum(1 for _ in open(self.inv_file) if not _.strip().startswith("#") and _.strip()),
        }
        atomic_write(backup_path / "manifest.json", json.dumps(manifest, indent=2))
        log.info("Backup created: %s (%d files)", backup_path, len(backed_up))
        return backup_path

    def restore(self, backup_path: Path) -> None:
        """Restore inventory and vault from a backup directory."""
        if not backup_path.exists():
            raise BackupError(f"Backup path not found: {backup_path}")

        manifest_file = backup_path / "manifest.json"
        if not manifest_file.exists():
            raise BackupError(f"No manifest.json found in backup: {backup_path}")

        with FileLock(self.lock_file):
            manifest = json.loads(manifest_file.read_text())
            for rel in manifest["files"]:
                src = backup_path / rel
                dest = BASE_DIR / rel
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)

        log.info(
            "Restored from backup %s (%d files, %d hosts)",
            backup_path,
            len(manifest["files"]),
            manifest.get("host_count", "?"),
        )

    # ------------------------------------------------------------------
    # Import from 7-field definition file (bootstrap only)
    # ------------------------------------------------------------------

    def import_definition_file(self, source: Path) -> tuple[int, dict[str, str]]:
        """
        Parse a 7-field bootstrap file (node ip user group hostname port password).
        Writes the 6-field inventory and returns (count, {node: password}).
        The source file MUST be deleted by the caller after import.
        """
        if not source.exists():
            raise ParseError(f"Definition file not found: {source}")

        records: list[HostRecord] = []
        passwords: dict[str, str] = {}
        seen_nodes: set[str] = set()
        seen_ips: set[str] = set()
        warnings: list[str] = []

        with open(source, encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, 1):
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split()
                if len(parts) != 7:
                    warnings.append(f"Line {lineno}: expected 7 fields, got {len(parts)} — skipped")
                    continue

                node_r, ip_r, user_r, group_r, host_r, port_r, pw_r = parts

                try:
                    node = validate_name(node_r, "node")
                    ip = validate_ip(ip_r)
                    user = validate_name(user_r, "user")
                    group = validate_name(group_r, "group")
                    hostname = validate_name(host_r, "hostname")
                    port = validate_port(port_r)
                except ValidationError as exc:
                    warnings.append(f"Line {lineno}: {exc} — skipped")
                    continue

                if node in seen_nodes:
                    warnings.append(f"Line {lineno}: duplicate node '{node}' — skipped")
                    continue
                if ip in seen_ips:
                    warnings.append(f"Line {lineno}: duplicate IP '{ip}' — skipped")
                    continue

                seen_nodes.add(node)
                seen_ips.add(ip)
                records.append(HostRecord(node, ip, user, group, hostname, port))
                passwords[node] = pw_r  # kept only in-process, never written to inventory

        for w in warnings:
            log.warning("Import: %s", w)

        with FileLock(self.lock_file):
            self.save(records)
            self.vault.sync(records, passwords)

        # Clear passwords from local dict (best-effort in CPython)
        for k in list(passwords.keys()):
            passwords[k] = "\x00" * len(passwords[k])

        log.info(
            "Imported %d host(s) from %s. "
            "DELETE THE SOURCE FILE NOW — it contained plaintext passwords.",
            len(records), source,
        )
        return len(records), {}

    # ------------------------------------------------------------------
    # Export (safe — no passwords)
    # ------------------------------------------------------------------

    def export(self, output: Path) -> None:
        """Export the current inventory to a JSON file (no secrets)."""
        records, warnings = self.load()
        for w in warnings:
            log.warning(w)
        data = build_inventory_json(records)
        atomic_write(output, json.dumps(data, indent=2))
        log.info("Inventory exported to %s (%d hosts)", output, len(records))


# ---------------------------------------------------------------------------
# Validation report
# ---------------------------------------------------------------------------

def run_validation(manager: InventoryManager) -> bool:
    """Run full validation and print a human-readable report. Returns True if clean."""
    try:
        records, warnings = manager.load()
    except ParseError as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        return False

    ok = True
    print(f"Inventory: {manager.inv_file}")
    print(f"Hosts loaded: {len(records)}")

    if warnings:
        ok = False
        print(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            print(f"  ⚠  {w}")
    else:
        print("  ✓ No parse warnings")

    # Cross-check vault
    try:
        vault_nodes = set(manager.vault.list_nodes())
        inv_nodes = {r.node for r in records}
        missing_in_vault = inv_nodes - vault_nodes
        orphan_in_vault = vault_nodes - inv_nodes

        if missing_in_vault:
            ok = False
            print(f"\nHosts missing vault entries ({len(missing_in_vault)}):")
            for n in sorted(missing_in_vault):
                print(f"  ⚠  {n}")
        else:
            print("  ✓ All hosts have vault entries")

        if orphan_in_vault:
            print(f"\nOrphan vault entries not in inventory ({len(orphan_in_vault)}):")
            for n in sorted(orphan_in_vault):
                print(f"  ℹ  {n}")
    except VaultError as exc:
        print(f"\n  ⚠ Could not read vault: {exc}")

    status = "PASS" if ok else "FAIL"
    print(f"\nValidation result: {status}")
    return ok


# ---------------------------------------------------------------------------
# Interactive prompts for --add-host / --update-host
# ---------------------------------------------------------------------------

def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"  {label}{suffix}: ").strip()
        if val:
            return val
        if default:
            return default
        print("    (required)")


def _prompt_secret(label: str) -> str:
    """Prompt for a password without echoing. Falls back to getpass."""
    import getpass
    while True:
        val = getpass.getpass(f"  {label}: ")
        if val:
            return val
        print("    (required)")


def interactive_add(manager: InventoryManager) -> None:
    print("=== Add New Host ===")
    node = _prompt("Node (Ansible hostname)")
    ip = _prompt("IP address")
    user = _prompt("SSH user", "root")
    group = _prompt("Group")
    hostname = _prompt("Linux hostname", node)
    port_str = _prompt("SSH port", str(CONFIG["default_ssh_port"]))
    password = _prompt_secret("Password (will be vaulted)")

    port = validate_port(port_str)
    manager.add_host(node, ip, user, group, hostname, port, password)
    print(f"✓ Host '{node}' added and password stored in vault.")


def interactive_update(manager: InventoryManager, node: str) -> None:
    records, _ = manager.load()
    target = next((r for r in records if r.node == node), None)
    if target is None:
        raise HostNotFoundError(f"Host '{node}' not found.")

    print(f"=== Update Host: {node} (leave blank to keep current) ===")
    ip = input(f"  IP [{target.ip}]: ").strip() or None
    user = input(f"  User [{target.user}]: ").strip() or None
    group = input(f"  Group [{target.group}]: ").strip() or None
    hostname = input(f"  Hostname [{target.hostname}]: ").strip() or None
    port_str = input(f"  Port [{target.ssh_port}]: ").strip()
    port = validate_port(port_str) if port_str else None

    import getpass
    pw_raw = getpass.getpass("  New password (blank = no change): ")
    password = pw_raw if pw_raw else None

    manager.update_host(
        node, ip=ip, user=user, group=group,
        hostname=hostname, ssh_port=port, password=password,
    )
    print(f"✓ Host '{node}' updated.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="inventory.py",
        description="Production-grade Ansible Inventory & Vault Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  inventory.py --list
  inventory.py --host master01
  inventory.py --validate
  inventory.py --sync-vault --def-file nodes.txt
  inventory.py --add-host
  inventory.py --delete-host compute001
  inventory.py --update-host gpu001
  inventory.py --backup
  inventory.py --restore backups/backup_20250101_120000
  inventory.py --export inventory_snapshot.json
  inventory.py --import nodes_with_passwords.txt
""",
    )

    # Ansible dynamic inventory protocol
    p.add_argument("--list", action="store_true",
                   help="Output full inventory JSON (Ansible dynamic inventory)")
    p.add_argument("--host", metavar="HOSTNAME",
                   help="Output hostvars JSON for a single host")

    # Management commands
    p.add_argument("--validate", action="store_true",
                   help="Validate inventory file and vault consistency")
    p.add_argument("--sync-vault", action="store_true",
                   help="Sync vault from a 7-field definition file (--def-file)")
    p.add_argument("--add-host", action="store_true",
                   help="Interactively add a new host")
    p.add_argument("--delete-host", metavar="HOSTNAME",
                   help="Remove a host from inventory and vault")
    p.add_argument("--update-host", metavar="HOSTNAME",
                   help="Interactively update an existing host")
    p.add_argument("--backup", action="store_true",
                   help="Create a timestamped backup")
    p.add_argument("--restore", metavar="BACKUP_DIR",
                   help="Restore from a backup directory")
    p.add_argument("--export", metavar="OUTPUT_FILE",
                   help="Export inventory JSON (no secrets) to a file")
    p.add_argument("--import", dest="import_file", metavar="DEF_FILE",
                   help="Bootstrap: import 7-field definition file, then delete it")

    # Options
    p.add_argument("--input-file", metavar="FILE",
                   help="Override inventory file path")
    p.add_argument("--def-file", metavar="FILE",
                   help="7-field definition file for --sync-vault")
    p.add_argument("--debug", action="store_true",
                   help="Enable DEBUG logging")
    p.add_argument("--no-delete", action="store_true",
                   help="With --import: keep the definition file after import (INSECURE)")

    return p


def main() -> int:  # returns exit code
    parser = build_parser()
    args = parser.parse_args()

    # Apply path overrides
    if args.input_file:
        CONFIG["inventory_file"] = Path(args.input_file)

    # Logging
    setup_logging(CONFIG["log_file"], debug=args.debug)

    manager = InventoryManager(CONFIG)

    try:
        # ---- Ansible dynamic inventory protocol (must be fast + silent on stderr) ----

        if args.list:
            records, warnings = manager.load()
            for w in warnings:
                log.warning(w)
            print(json.dumps(build_inventory_json(records), indent=2))
            return 0

        if args.host:
            records, _ = manager.load()
            hv = next(
                (r.to_hostvars() for r in records if r.node == args.host),
                {},
            )
            print(json.dumps(hv, indent=2))
            return 0

        # ---- Management commands ----

        if args.validate:
            ok = run_validation(manager)
            return 0 if ok else 1

        if args.sync_vault:
            if not args.def_file:
                print("Error: --sync-vault requires --def-file <7-field-file>", file=sys.stderr)
                return 1
            def_path = Path(args.def_file)
            count, _ = manager.import_definition_file(def_path)
            print(f"✓ Vault synced for {count} host(s).")
            print(f"  ⚠  DELETE {def_path} — it contained plaintext passwords.")
            return 0

        if args.add_host:
            interactive_add(manager)
            return 0

        if args.delete_host:
            manager.delete_host(args.delete_host)
            print(f"✓ Host '{args.delete_host}' deleted.")
            return 0

        if args.update_host:
            interactive_update(manager, args.update_host)
            return 0

        if args.backup:
            path = manager.backup()
            print(f"✓ Backup created: {path}")
            return 0

        if args.restore:
            manager.restore(Path(args.restore))
            print(f"✓ Restored from: {args.restore}")
            return 0

        if args.export:
            out = Path(args.export)
            manager.export(out)
            print(f"✓ Exported to: {out}")
            return 0

        if args.import_file:
            src = Path(args.import_file)
            count, _ = manager.import_definition_file(src)
            print(f"✓ Imported {count} host(s) from {src}.")
            if not args.no_delete:
                src.unlink()
                print(f"✓ Source file deleted: {src}")
            else:
                print(f"  ⚠  WARNING: {src} was NOT deleted and still contains plaintext passwords!")
            return 0

        parser.print_help()
        return 1

    except (InventoryError, PermissionError, OSError) as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130
    except Exception as exc:  # pragma: no cover
        log.exception("Unexpected error: %s", exc)
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
