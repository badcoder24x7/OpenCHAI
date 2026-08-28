"""
OpenCHAI GUI — Inventory CLI Bridge  (v7 — real automation script integration)

Root-cause fix for "bulk import claims success but nodes don't actually get
added / passwords silently stop working":

The GUI used to have its OWN, parallel re-implementation of inventory
management (the old services/inventory_def_service.py write path) and its
OWN, parallel password-vaulting scheme (services/vault_service.py, writing
per-host `ansible_password: !vault |` blocks directly into host_vars/).

That is a *different* storage design than what the real, deployed
automation tree actually uses — automation/ansible/inventory.py — which
keeps ALL node passwords in a single encrypted
automation/ansible/inventory/group_vars/all/vault.yml (`vault_passwords:
{node: password}`) and writes host_vars/<node>.yml as a thin stub that
*references* that central vault:

    ansible_password: "{{ vault_passwords[inventory_hostname] }}"

Whichever of the two systems wrote host_vars last would silently stomp the
other's password storage — e.g. a bulk import that (re)writes every host's
stub back to the reference form would break a node whose password had only
ever been registered via the GUI's separate per-host vault_service path,
because that password was never entered into vault_passwords in the first
place. That's exactly the class of bug behind "worked in the popup, didn't
actually work."

The fix: stop maintaining a second implementation. This module loads the
REAL automation/ansible/inventory.py in-process (it's pure stdlib — no
extra dependency) and every mutating GUI operation — add / update / delete
/ bulk import — goes through its InventoryManager / VaultManager, which is
the same code path bootstrap_import.py and the inventory.sh dynamic
inventory shim use. One system of record, used everywhere.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import settings

logger = logging.getLogger(__name__)

_module = None
_manager = None
_lock = threading.Lock()


class BridgeError(RuntimeError):
    """Raised when the real inventory.py can't be loaded or a call into it fails."""


def _inventory_script_path() -> Path:
    if not settings.ANSIBLE_DIR:
        raise BridgeError(
            "ANSIBLE_DIR is not configured (OPENCHAI_ROOT unset?) — cannot "
            "locate automation/ansible/inventory.py."
        )
    path = Path(settings.ANSIBLE_DIR) / "inventory.py"
    if not path.exists():
        raise BridgeError(f"Real inventory script not found at {path}.")
    return path


def _load_module():
    """Import automation/ansible/inventory.py by file path, once per process.
    __file__ inside that module resolves to its real location, so its own
    BASE_DIR / CONFIG path derivation (inventory_def.txt, vault.yml,
    host_vars/, .vault_pass, locks, logs) all resolve correctly with zero
    extra configuration on our side — we're just running the same script
    Ansible itself runs, in-process instead of via inventory.sh."""
    script = _inventory_script_path()
    spec = importlib.util.spec_from_file_location("openchai_real_inventory", script)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["openchai_real_inventory"] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        raise BridgeError(f"Failed to load {script}: {exc}") from exc
    return mod


def _get() -> Tuple["object", "object"]:
    """Return (module, manager), lazily initialised once per process."""
    global _module, _manager
    if _manager is None:
        with _lock:
            if _manager is None:
                mod = _load_module()
                mgr = mod.InventoryManager(mod.CONFIG)
                _module, _manager = mod, mgr
    return _module, _manager


def inventory_file_path() -> str:
    _, m = _get()
    return str(m.inv_file)


def backup_if_enabled(enabled: bool) -> None:
    """Snapshot inventory_def.txt + vault.yml + all host_vars before a
    mutating operation, using the real script's own timestamped backup() —
    a fuller snapshot than the GUI's old single-file backup, since it also
    protects the vault and host_vars stubs, not just inventory_def.txt."""
    if not enabled:
        return
    mod, m = _get()
    try:
        m.backup()
    except mod.InventoryError as exc:
        logger.warning("Pre-write backup failed (continuing anyway): %s", exc)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def list_nodes() -> List[Dict[str, object]]:
    """Return every node as a dict matching the GUI's existing column
    names, plus password_set computed from the REAL central vault (not a
    per-file heuristic)."""
    mod, m = _get()
    try:
        records, warnings = m.load()
    except mod.ParseError as exc:
        raise BridgeError(str(exc)) from exc
    for w in warnings:
        logger.warning("inventory_def.txt: %s", w)

    pw_map: Dict[str, str] = {}
    try:
        pw_map = m.vault._parse_vault_yaml(m.vault.decrypt_vault())
    except Exception as exc:
        logger.warning("Could not read vault for password_set status: %s", exc)

    return [
        {
            "ansible_hostname": r.node,
            "ip": r.ip,
            "ansible_user": r.user,
            "group": r.group,
            "hostname": r.hostname,
            "ssh_port": str(r.ssh_port),
            "password_set": bool(pw_map.get(r.node)),
        }
        for r in records
    ]


def raw_file_content() -> str:
    path = Path(inventory_file_path())
    return path.read_text(encoding="utf-8") if path.exists() else ""


def get_connection_info(node: str) -> Dict[str, object]:
    """Return {ip, user, port, password} for one node, for live actions like
    the SSH-test endpoint. The password is decrypted from the central vault
    transiently in memory and is never written anywhere by this call."""
    mod, m = _get()
    try:
        records, _ = m.load()
    except mod.ParseError as exc:
        raise BridgeError(str(exc)) from exc
    rec = next((r for r in records if r.node == node), None)
    if rec is None:
        raise BridgeError(f"Host '{node}' not found.")

    password = None
    try:
        pw_map = m.vault._parse_vault_yaml(m.vault.decrypt_vault())
        password = pw_map.get(node)
    except Exception as exc:
        logger.warning("Could not decrypt vault password for '%s': %s", node, exc)

    return {"ip": rec.ip, "user": rec.user, "port": rec.ssh_port, "password": password}


# ---------------------------------------------------------------------------
# Single-host CRUD — mirrors InventoryManager.add_host/update_host but with
# GUI-appropriate optional-password semantics (the CLI's own convenience
# wrappers assume a password is always supplied).
# ---------------------------------------------------------------------------

def add_node(
    node: str, ip: str, user: str, group: str,
    hostname: str, ssh_port: str, password: str = "", backup: bool = True,
) -> int:
    mod, m = _get()
    backup_if_enabled(backup)
    try:
        with mod.FileLock(m.lock_file):
            records, _ = m.load()
            if node in {r.node for r in records}:
                raise BridgeError(f"Host '{node}' already exists.")
            ip_val = mod.validate_ip(ip)
            if ip_val in {r.ip for r in records}:
                raise BridgeError(f"IP {ip_val} is already assigned to another host.")
            user_v  = mod.validate_name(user, "user")
            group_v = mod.validate_name(group, "group")
            host_v  = mod.validate_name(hostname or node, "hostname")
            port_v  = mod.validate_port(str(ssh_port))

            record = mod.HostRecord(node, ip_val, user_v, group_v, host_v, port_v)
            records.append(record)
            m.save(records)

            if password:
                m.vault.sync(records, {node: password})
            else:
                # No credential yet — still write the reference-style stub
                # so the node is playbook-ready the moment a password IS
                # set later (via this same bridge), and so nothing else
                # ever needs to touch host_vars for this node again.
                m.vault._write_host_vars_stub(record)
            return len(records)
    except mod.InventoryError as exc:
        raise BridgeError(str(exc)) from exc


def update_node(
    node: str,
    *,
    ip: Optional[str] = None,
    user: Optional[str] = None,
    group: Optional[str] = None,
    hostname: Optional[str] = None,
    ssh_port: Optional[str] = None,
    password: Optional[str] = None,       # None=unchanged, ""=clear, else=set
    backup: bool = True,
) -> int:
    mod, m = _get()
    backup_if_enabled(backup)
    try:
        with mod.FileLock(m.lock_file):
            records, _ = m.load()
            target = next((r for r in records if r.node == node), None)
            if target is None:
                raise BridgeError(f"Host '{node}' not found.")

            if ip is not None:
                ip_val = mod.validate_ip(ip)
                if ip_val in {r.ip for r in records if r.node != node}:
                    raise BridgeError(f"IP {ip_val} is already assigned to another host.")
                target.ip = ip_val
            if user is not None:
                target.user = mod.validate_name(user, "user")
            if group is not None:
                target.group = mod.validate_name(group, "group")
            if hostname is not None:
                target.hostname = mod.validate_name(hostname, "hostname")
            if ssh_port is not None:
                target.ssh_port = mod.validate_port(str(ssh_port))

            m.save(records)

            if password is None:
                # Unchanged — but keep the host_vars stub in sync with any
                # field edits above (user/ip/etc).
                m.vault._write_host_vars_stub(target)
            elif password == "":
                m.vault.delete(node)          # explicit clear
                m.vault._write_host_vars_stub(target)
            else:
                m.vault.sync(records, {node: password})

            return len(records)
    except mod.InventoryError as exc:
        raise BridgeError(str(exc)) from exc


def delete_node(node: str, backup: bool = True) -> int:
    mod, m = _get()
    backup_if_enabled(backup)
    try:
        with mod.FileLock(m.lock_file):
            records, _ = m.load()
            new_records = [r for r in records if r.node != node]
            if len(new_records) == len(records):
                raise BridgeError(f"Host '{node}' not found.")
            m.save(new_records)
            try:
                m.vault.delete(node)
            except mod.VaultError as exc:
                logger.warning("Vault cleanup failed for '%s': %s", node, exc)
            stub = m.host_vars_dir / f"{node}.yml"
            if stub.exists():
                stub.unlink()
            return len(new_records)
    except mod.InventoryError as exc:
        raise BridgeError(str(exc)) from exc


# ---------------------------------------------------------------------------
# Bulk import — 7 fields per line: node ip user group hostname ssh_port password
#
# IMPORTANT: the real script's own `import_definition_file()` is a
# BOOTSTRAP-ONLY operation — it *overwrites* inventory_def.txt with just
# the file's records, it does not merge with what's already there (that's
# correct for a brand-new cluster's one-time setup, but would silently wipe
# every existing node if called again from the GUI for "add more nodes").
#
# So this function uses the exact same validated building blocks the real
# script uses — HostRecord, validate_ip/name/port, FileLock, save(),
# vault.sync() — but merges the newly parsed rows into the EXISTING
# inventory instead of replacing it, and reports per-row skip reasons
# instead of silently discarding bad rows.
#
# Commas are normalised to whitespace first, since the underlying format
# bootstrap_import.py's own docstring advertises ("space or comma
# separated") but only whitespace-splits in practice.
# ---------------------------------------------------------------------------

def bulk_import(raw_text: str, backup: bool = True) -> Dict[str, object]:
    mod, m = _get()
    backup_if_enabled(backup)

    added: List = []          # HostRecord objects
    added_passwords: Dict[str, str] = {}
    skipped: List[Dict[str, object]] = []

    try:
        with mod.FileLock(m.lock_file):
            existing, _ = m.load()
            existing_nodes = {r.node for r in existing}
            existing_ips   = {r.ip for r in existing}
            seen_nodes_in_file: set = set()
            seen_ips_in_file: set = set()

            for lineno, raw_line in enumerate(raw_text.splitlines(), start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.replace(",", " ").split()

                if len(parts) != 7:
                    skipped.append({
                        "row": lineno, "hostname": parts[0] if parts else "(blank)",
                        "reason": f"Expected 7 fields (node ip user group hostname "
                                  f"ssh_port password), got {len(parts)}.",
                    })
                    continue

                node_r, ip_r, user_r, group_r, host_r, port_r, pw_r = parts
                try:
                    node = mod.validate_name(node_r, "node")
                    ip   = mod.validate_ip(ip_r)
                    user = mod.validate_name(user_r, "user")
                    group = mod.validate_name(group_r, "group")
                    hostname = mod.validate_name(host_r, "hostname")
                    port = mod.validate_port(port_r)
                except mod.ValidationError as exc:
                    skipped.append({"row": lineno, "hostname": node_r, "reason": str(exc)})
                    continue

                if node in existing_nodes or node in seen_nodes_in_file:
                    skipped.append({"row": lineno, "hostname": node, "reason": "Duplicate — already exists."})
                    continue
                if ip in existing_ips or ip in seen_ips_in_file:
                    skipped.append({"row": lineno, "hostname": node, "reason": f"IP {ip} already in use."})
                    continue
                if not pw_r:
                    skipped.append({"row": lineno, "hostname": node, "reason": "Password field is required for bulk import."})
                    continue

                seen_nodes_in_file.add(node)
                seen_ips_in_file.add(ip)
                record = mod.HostRecord(node, ip, user, group, hostname, port)
                added.append(record)
                added_passwords[node] = pw_r

            if added:
                merged = existing + added
                m.save(merged)
                m.vault.sync(merged, added_passwords)
            total = len(existing) + len(added)
    except mod.InventoryError as exc:
        raise BridgeError(str(exc)) from exc
    finally:
        # Best-effort scrub of plaintext passwords from the local dict.
        for k in list(added_passwords.keys()):
            added_passwords[k] = "\x00" * len(added_passwords[k])

    return {
        "total": total,
        "added": len(added),
        "added_names": [r.node for r in added],
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Startup diagnostics
# ---------------------------------------------------------------------------

def check_bridge_readiness() -> None:
    """Log whether the real inventory.py loads cleanly and its config paths
    resolve, mirroring vault_service.check_vault_readiness()'s startup
    pattern. Never raises — this is advisory only."""
    try:
        mod, m = _get()
        logger.info(
            "Inventory bridge OK — using %s (inventory_file=%s)",
            _inventory_script_path(), m.inv_file,
        )
    except BridgeError as exc:
        logger.warning("Inventory bridge not ready: %s", exc)
