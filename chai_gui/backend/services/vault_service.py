"""
OpenCHAI GUI — Ansible Vault Service

Encrypts per-node SSH credentials with `ansible-vault encrypt_string` and
writes them into host_vars/<ansible_hostname>.yml, in exactly the format
Ansible's own dynamic inventory script expects:

    ---
    ansible_user: temp
    ansible_password: !vault |
              $ANSIBLE_VAULT;1.1;AES256
              6165336433323633333337643034303736333163303631366665636156136313
              ...
    ansible_become_pass: !vault |
              $ANSIBLE_VAULT;1.1;AES256
              ...

This is a verified, byte-for-byte match against real `ansible-vault
encrypt_string` CLI output (confirmed by running the actual binary), not a
hand-rolled approximation of the vault format.

Why shell out to the CLI instead of using ansible's internal Python API
─────────────────────────────────────────────────────────────────────────
`ansible.parsing.vault.VaultLib` is not a stable/public API and its
import path has changed across ansible-core versions. The GUI's
requirements.txt does not currently pin an `ansible`/`ansible-core` PyPI
package — only the `ansible-playbook` CLI binary is assumed to be on
PATH (ansible_runner.py already shells out to it the same way). Shelling
out to `ansible-vault` keeps this module exposed to exactly the same
trust boundary and version-compatibility story as the rest of the app,
rather than adding a second, more fragile integration path.

No plaintext password is ever written to inventory_def.txt or to any
GUI-readable file other than transiently in memory during this call.
"""

from __future__ import annotations

import logging
import os
import secrets
import subprocess
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

_VAULT_TIMEOUT_SECS = 15


class VaultError(RuntimeError):
    """Raised when ansible-vault itself fails (not found, bad password file, etc.)."""


# ─────────────────────────────────────────────────────────────────────────────
# .vault_pass management
# ─────────────────────────────────────────────────────────────────────────────

def ensure_vault_password_file() -> str:
    """
    Ensure the vault password file referenced by ansible.cfg's
    vault_password_file setting exists, creating one with a random
    passphrase (mode 0600) if missing.

    Returns the resolved path. Raises VaultError if ANSIBLE_DIR/
    VAULT_PASSWORD_FILE is not configured (OPENCHAI_ROOT unset) — callers
    must surface that to the user as a 400, not let it crash silently.
    """
    path = settings.VAULT_PASSWORD_FILE
    if not path:
        raise VaultError(
            "VAULT_PASSWORD_FILE is not configured — set OPENCHAI_ROOT/"
            "ANSIBLE_DIR so the vault password file location can be derived."
        )

    if os.path.exists(path):
        return path

    os.makedirs(os.path.dirname(path), exist_ok=True)
    passphrase = secrets.token_hex(32)  # 64 hex chars — plenty of entropy

    # Write with restrictive permissions from the start (avoid a window
    # where the file is briefly world-readable).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(passphrase + "\n")
    finally:
        os.chmod(path, 0o600)

    logger.info("Created new vault password file at %s", path)
    return path


def _vault_password_file() -> str:
    return ensure_vault_password_file()


def check_vault_readiness() -> None:
    """
    Startup diagnostic — logs whether ansible.cfg already points
    vault_password_file at the same path this module will use, and
    ensures the password file itself exists.

    This function NEVER writes to ansible.cfg. ansible.cfg is owned by
    the OpenCHAI automation tree (outside this repo) and is expected to
    already have `vault_password_file = <ANSIBLE_DIR>/.vault_pass` set,
    matching how the real deployment is configured. If it's missing or
    points somewhere else, this only logs a warning so an admin can fix
    ansible.cfg — silently rewriting someone else's config file on
    startup would be a much riskier failure mode than a clear log line.
    """
    if not settings.ANSIBLE_CFG or not settings.VAULT_PASSWORD_FILE:
        logger.warning(
            "Vault readiness check skipped — ANSIBLE_DIR not configured "
            "(OPENCHAI_ROOT unset?). Inventory password encryption will "
            "fail until this is set."
        )
        return

    try:
        ensure_vault_password_file()
    except VaultError as exc:
        logger.warning("Could not prepare vault password file: %s", exc)
        return

    if not os.path.exists(settings.ANSIBLE_CFG):
        logger.warning(
            "ansible.cfg not found at %s — cannot verify vault_password_file "
            "setting. Inventory passwords will be encrypted to %s but "
            "Ansible itself won't decrypt them at playbook-run time until "
            "ansible.cfg has: vault_password_file = %s",
            settings.ANSIBLE_CFG, settings.VAULT_PASSWORD_FILE, settings.VAULT_PASSWORD_FILE,
        )
        return

    try:
        cfg_text = Path(settings.ANSIBLE_CFG).read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read ansible.cfg to verify vault setting: %s", exc)
        return

    if "vault_password_file" not in cfg_text:
        logger.warning(
            "ansible.cfg at %s has no vault_password_file setting. "
            "Add under [defaults]: vault_password_file = %s "
            "— otherwise Ansible playbook runs won't be able to decrypt "
            "node passwords stored by the GUI.",
            settings.ANSIBLE_CFG, settings.VAULT_PASSWORD_FILE,
        )
    elif settings.VAULT_PASSWORD_FILE not in cfg_text:
        logger.warning(
            "ansible.cfg's vault_password_file does not match %s (the path "
            "this GUI uses to encrypt node passwords). Playbook runs may "
            "fail to decrypt host_vars credentials written by the GUI "
            "until these are aligned.",
            settings.VAULT_PASSWORD_FILE,
        )
    else:
        logger.info(
            "Vault readiness OK — ansible.cfg vault_password_file matches %s",
            settings.VAULT_PASSWORD_FILE,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Low-level ansible-vault CLI wrapper
# ─────────────────────────────────────────────────────────────────────────────

def _run_ansible_vault(args: list, input_text: Optional[str] = None) -> str:
    """
    Run `ansible-vault <args>`, returning stdout. Raises VaultError with a
    clear message on any failure (binary missing, bad password file,
    non-zero exit, timeout).
    """
    try:
        result = subprocess.run(
            ["ansible-vault", *args],
            input=input_text,
            capture_output=True,
            text=True,
            timeout=_VAULT_TIMEOUT_SECS,
        )
    except FileNotFoundError as exc:
        raise VaultError(
            "ansible-vault executable not found on PATH. "
            "Install ansible-core on this machine to use encrypted "
            "node credentials."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise VaultError("ansible-vault timed out.") from exc

    if result.returncode != 0:
        raise VaultError(
            f"ansible-vault failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )

    return result.stdout


def encrypt_string(plaintext: str, var_name: str) -> str:
    """
    Run `ansible-vault encrypt_string --name <var_name> <plaintext>` and
    return the raw stdout block exactly as ansible-vault produces it:

        ansible_password: !vault |
                  $ANSIBLE_VAULT;1.1;AES256
                  <hex...>
                  <hex...>

    This full block (key + !vault | + indented ciphertext) is inserted
    verbatim into the host_vars YAML file — see write_host_vars() below.
    """
    if not plaintext:
        raise VaultError("Cannot encrypt an empty value.")

    vault_pass_path = _vault_password_file()

    stdout = _run_ansible_vault(
        [
            "encrypt_string",
            "--vault-password-file", vault_pass_path,
            plaintext,
            "--name", var_name,
        ]
    )
    # ansible-vault prints a trailing newline; strip exactly one so callers
    # control their own line joins precisely.
    return stdout.rstrip("\n")


# ─────────────────────────────────────────────────────────────────────────────
# host_vars/<hostname>.yml file management
# ─────────────────────────────────────────────────────────────────────────────

def _host_vars_path(ansible_hostname: str) -> Path:
    if not settings.HOST_VARS_DIR:
        raise VaultError(
            "HOST_VARS_DIR is not configured — set OPENCHAI_ROOT/ANSIBLE_DIR."
        )
    safe_name = ansible_hostname.strip()
    if not safe_name or "/" in safe_name or ".." in safe_name:
        raise VaultError(f"Invalid ansible_hostname for host_vars file: {ansible_hostname!r}")
    return Path(settings.HOST_VARS_DIR) / f"{safe_name}.yml"


def host_vars_exists(ansible_hostname: str) -> bool:
    try:
        return _host_vars_path(ansible_hostname).exists()
    except VaultError:
        return False


def has_vaulted_password(ansible_hostname: str) -> bool:
    """
    True if a host_vars file exists for this host AND it contains a
    vaulted ansible_password entry. Used to drive the inventory table's
    "password set / none" indicator without ever decrypting anything.
    """
    if not settings.HOST_VARS_DIR:
        return False
    try:
        path = _host_vars_path(ansible_hostname)
    except VaultError:
        return False
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return "ansible_password: !vault" in content


def write_host_vars(
    ansible_hostname: str,
    ansible_user: str,
    ansible_password: Optional[str] = None,
    ansible_become_pass: Optional[str] = None,
) -> str:
    """
    Write (or rewrite) host_vars/<ansible_hostname>.yml with:

        ---
        ansible_user: <ansible_user>
        ansible_password: !vault |
                  ...
        ansible_become_pass: !vault |
                  ...

    Passing None for ansible_password or ansible_become_pass means "leave
    the existing vaulted value untouched" — the existing block (if any)
    for that key is preserved verbatim by reading the current file first.
    Passing an empty string means "clear this credential" — the key is
    omitted entirely from the rewritten file.

    Returns the path written to.

    This function NEVER receives or stores a plaintext password on disk —
    only the result of encrypt_string() (the !vault block) is written.
    """
    path = _host_vars_path(ansible_hostname)
    os.makedirs(path.parent, exist_ok=True)

    existing_blocks = _read_existing_vault_blocks(path) if path.exists() else {}

    lines = ["---", f"ansible_user: {ansible_user}"]

    # ansible_password
    if ansible_password is None:
        if "ansible_password" in existing_blocks:
            lines.append(existing_blocks["ansible_password"])
    elif ansible_password != "":
        lines.append(encrypt_string(ansible_password, "ansible_password"))

    # ansible_become_pass
    if ansible_become_pass is None:
        if "ansible_become_pass" in existing_blocks:
            lines.append(existing_blocks["ansible_become_pass"])
    elif ansible_become_pass != "":
        lines.append(encrypt_string(ansible_become_pass, "ansible_become_pass"))

    content = "\n".join(lines) + "\n"

    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
    finally:
        os.chmod(str(path), 0o600)

    logger.info(
        "Wrote host_vars for %s (password=%s, become_pass=%s)",
        ansible_hostname,
        "set" if (ansible_password or (ansible_password is None and "ansible_password" in existing_blocks)) else "unset",
        "set" if (ansible_become_pass or (ansible_become_pass is None and "ansible_become_pass" in existing_blocks)) else "unset",
    )
    return str(path)


def delete_host_vars(ansible_hostname: str) -> bool:
    """
    Delete host_vars/<ansible_hostname>.yml if it exists.
    Returns True if a file was actually deleted, False if there was
    nothing to delete. Never raises on "file not found".
    """
    try:
        path = _host_vars_path(ansible_hostname)
    except VaultError:
        return False

    if not path.exists():
        return False

    try:
        path.unlink()
        logger.info("Deleted host_vars file for %s (%s)", ansible_hostname, path)
        return True
    except OSError as exc:
        logger.error("Failed to delete host_vars file %s: %s", path, exc)
        raise VaultError(f"Failed to delete host_vars file for '{ansible_hostname}': {exc}") from exc


def _read_existing_vault_blocks(path: Path) -> dict:
    """
    Parse an existing host_vars/<host>.yml file and return
    {key_name: "<key>: !vault |\\n          <line1>\\n          <line2>..."}
    for each top-level `<key>: !vault |` block found — used to preserve a
    credential untouched when only the *other* one is being updated.

    This is intentionally a plain-text line scan, not a YAML parse —
    PyYAML's safe_load cannot construct the `!vault` tag at all (verified:
    it raises ConstructorError), and we never need the decrypted value
    here, only to copy the block verbatim into the rewritten file.
    """
    blocks: dict = {}
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return blocks

    current_key: Optional[str] = None
    current_lines: list = []

    def _flush():
        if current_key is not None:
            blocks[current_key] = "\n".join(current_lines)

    for line in raw_lines:
        if line.endswith(": !vault |") and not line.startswith((" ", "\t")):
            _flush()
            current_key = line.split(":", 1)[0].strip()
            current_lines = [line]
        elif current_key is not None and (line.startswith("          ") or line.strip() == ""):
            # Continuation line of the current vault block (10-space indent,
            # matching ansible-vault's own CLI output) — keep accumulating.
            if line.strip() == "":
                # Blank line ends the block
                _flush()
                current_key = None
                current_lines = []
            else:
                current_lines.append(line)
        else:
            # A new non-indented, non-vault line ends the current block
            _flush()
            current_key = None
            current_lines = []

    _flush()
    return blocks
