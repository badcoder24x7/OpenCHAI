"""
OpenCHAI GUI - Inventory Def Service
Reads and writes Ansible inventory_def.txt in its exact space-separated format:

  ansible_hostname  ip  ansible_user  group  hostname  ssh_port

Lines starting with # are treated as comments and preserved.

Password handling (v6 — Ansible Vault)
───────────────────────────────────────
ansible_password is NO LONGER a column in this file. Storing it here
meant every node's SSH password sat in plaintext on disk, readable by
anyone who could read inventory_def.txt.

Passwords are now encrypted with `ansible-vault encrypt_string` and
written to host_vars/<ansible_hostname>.yml (see services/vault_service.py)
— this is exactly the file Ansible's own dynamic inventory script
(inventory_def.py / inventory.sh, both outside this repo) reads at
playbook-run time via ansible.cfg's vault_password_file setting.

This module's read/write functions now operate on the 6-column schema
only. Password get/set is handled by routes/inventory_def.py calling
into vault_service directly — this service module has no password logic
at all anymore, by design, so a plaintext password can never accidentally
end up back in this file through this code path.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Dict, List, Optional

from config import settings
from services.backup_service import backup_and_write

logger = logging.getLogger(__name__)

# Column order — MUST match the file format exactly.
# ansible_password was removed from this schema (see module docstring) —
# do not add it back here even temporarily; password storage lives only
# in services/vault_service.py's encrypted host_vars files.
COLUMNS = [
    "ansible_hostname",
    "ip",
    "ansible_user",
    "group",
    "hostname",
    "ssh_port",
]

HEADER_LINE = "# ansible_hostname  ip  ansible_user  group  hostname  ssh_port"


def _inventory_def_path() -> str:
    return os.path.join(settings.ANSIBLE_DIR, "inventory", "inventory_def.txt")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def read_inventory_def() -> List[Dict[str, str]]:
    """Parse inventory_def.txt and return a list of node dicts (no password field)."""
    path = _inventory_def_path()
    if not os.path.exists(path):
        logger.warning("inventory_def.txt not found at %s — returning empty list", path)
        return []

    nodes: List[Dict[str, str]] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < len(COLUMNS):
                # Pad missing columns with empty string
                parts += [""] * (len(COLUMNS) - len(parts))
            node = dict(zip(COLUMNS, parts[:len(COLUMNS)]))
            nodes.append(node)

    return nodes


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def _safe_col(value: str, default: str = "") -> str:
    """
    Return a file-safe column value.
    Empty / whitespace-only strings are replaced with *default* so the
    space-separated parser always finds the expected number of columns.
    """
    v = str(value).strip()
    return v if v else default


def write_inventory_def(nodes: List[Dict[str, str]], backup: bool = True) -> str:
    """
    Serialize *nodes* back to inventory_def.txt format and write atomically.

    Column-shift defence
    --------------------
    inventory_def.txt is parsed by splitting on whitespace, so an empty
    column causes every subsequent column to shift one position to the left.
    We defend against this by running every column through _safe_col(),
    which substitutes a safe non-empty default when the value is blank:
        • group    → compute
        • ssh_port → 22
        • hostname → falls back to ansible_hostname

    Returns the rendered file content.
    """
    col_defaults = {
        "ansible_hostname": "unknown",
        "ip":               "0.0.0.0",
        "ansible_user":     "root",
        "group":            "compute",
        "hostname":         "",          # filled from ansible_hostname below
        "ssh_port":         "22",
    }

    rows_safe = []
    for node in nodes:
        hostname_fallback = _safe_col(node.get("ansible_hostname", ""), col_defaults["ansible_hostname"])
        rows_safe.append([
            hostname_fallback,
            _safe_col(node.get("ip",           ""), col_defaults["ip"]),
            _safe_col(node.get("ansible_user", ""), col_defaults["ansible_user"]),
            _safe_col(node.get("group",        ""), col_defaults["group"]),
            _safe_col(node.get("hostname",     ""), hostname_fallback),
            _safe_col(node.get("ssh_port",     ""), col_defaults["ssh_port"]),
        ])

    # Min widths from the header comment tokens
    header_tokens = HEADER_LINE.lstrip("# ").split()
    widths = [len(t) for t in header_tokens]
    for row in rows_safe:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    lines = [
        HEADER_LINE,
        "#",
        "# Auto-managed by OpenCHAI GUI — edit via the Inventory Management page",
        "#",
    ]
    for row in rows_safe:
        # Left-justify every column to its computed width except the last
        padded = [val.ljust(widths[i]) for i, val in enumerate(row[:-1])]
        padded.append(row[-1])          # ssh_port — no trailing spaces needed
        lines.append("  ".join(padded).rstrip())

    content = "\n".join(lines) + "\n"
    path = _inventory_def_path()
    backup_and_write(path, content, enabled=backup)
    logger.info("inventory_def.txt written with %d nodes", len(nodes))
    return content


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

def add_node(node: Dict[str, str], backup: bool = True) -> List[Dict[str, str]]:
    nodes = read_inventory_def()
    if any(n["ansible_hostname"] == node["ansible_hostname"] for n in nodes):
        raise ValueError(f"Node '{node['ansible_hostname']}' already exists.")
    # Strip any ansible_password key the caller might still pass in —
    # this module never persists it; routes/inventory_def.py is
    # responsible for routing it to vault_service instead.
    nodes.append({k: v for k, v in node.items() if k in COLUMNS})
    write_inventory_def(nodes, backup=backup)
    return nodes


def update_node(ansible_hostname: str, updates: Dict[str, str], backup: bool = True) -> List[Dict[str, str]]:
    nodes = read_inventory_def()
    updates = {k: v for k, v in updates.items() if k in COLUMNS}
    for i, n in enumerate(nodes):
        if n["ansible_hostname"] == ansible_hostname:
            nodes[i] = {**n, **updates}
            write_inventory_def(nodes, backup=backup)
            return nodes
    raise KeyError(f"Node '{ansible_hostname}' not found.")


def delete_node(ansible_hostname: str, backup: bool = True) -> List[Dict[str, str]]:
    nodes = read_inventory_def()
    new_nodes = [n for n in nodes if n["ansible_hostname"] != ansible_hostname]
    if len(new_nodes) == len(nodes):
        raise KeyError(f"Node '{ansible_hostname}' not found.")
    write_inventory_def(new_nodes, backup=backup)
    return new_nodes


def bulk_import_csv(csv_text: str, backup: bool = True) -> Dict[str, object]:
    """
    Import nodes from CSV text.
    Expected header: ansible_hostname,ip,ansible_user,group,hostname,ssh_port

    Note: bulk CSV import intentionally does NOT accept a password column.
    Bulk-imported nodes are created without an encrypted credential; an
    admin must set each node's password individually afterward via the
    Inventory Management UI (which routes it through vault_service).
    This avoids ever having a plaintext password sitting in a pasted CSV
    blob inside an HTTP request body/log.

    Returns a dict with the merged node list plus per-row outcome details,
    instead of silently discarding rows that didn't parse — a CSV exported
    with different header casing/spacing (e.g. "Ansible_Hostname" or
    " ansible_hostname") used to fall through to an empty string for every
    field with no error surfaced, so the row vanished while the UI still
    reported "Import complete."
    """
    import csv, io

    reader = csv.DictReader(io.StringIO(csv_text))
    # Case/whitespace-tolerant header lookup: "Ansible_Hostname", " ip ",
    # "AnsibleUser" etc. all resolve to the correct column.
    def _norm(s: str) -> str:
        return (s or "").strip().lower().replace(" ", "").replace("_", "")

    fieldnames = reader.fieldnames or []
    header_map: Dict[str, str] = {}
    for col in COLUMNS:
        for fn in fieldnames:
            if _norm(fn) == _norm(col):
                header_map[col] = fn
                break

    added: List[Dict[str, str]] = []
    skipped: List[Dict[str, str]] = []

    existing = read_inventory_def()
    existing_names = {n["ansible_hostname"] for n in existing}
    seen_in_file: set = set()

    for i, row in enumerate(reader, start=2):  # start=2: header is line 1
        node: Dict[str, str] = {}
        for col in COLUMNS:
            src_key = header_map.get(col)
            node[col] = (row.get(src_key, "") if src_key else "").strip()

        errors = validate_node(node)
        hostname = node.get("ansible_hostname")

        if not hostname:
            skipped.append({"row": i, "hostname": "(blank)", "reason": "ansible_hostname is required."})
            continue
        if errors:
            skipped.append({"row": i, "hostname": hostname, "reason": "; ".join(errors)})
            continue
        if hostname in existing_names or hostname in seen_in_file:
            skipped.append({"row": i, "hostname": hostname, "reason": "Duplicate — already exists."})
            continue

        seen_in_file.add(hostname)
        added.append(node)

    merged = existing + added
    if added:
        write_inventory_def(merged, backup=backup)

    return {"nodes": merged, "added": added, "skipped": skipped}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_IP_RE = re.compile(
    r"^(\d{1,3}\.){3}\d{1,3}$"
)

def validate_node(node: Dict[str, str]) -> List[str]:
    """Return list of validation error messages (empty = valid)."""
    errors: List[str] = []
    if not node.get("ansible_hostname"):
        errors.append("ansible_hostname is required.")
    if not node.get("ip"):
        errors.append("ip is required.")
    elif not _IP_RE.match(node["ip"]):
        errors.append(f"ip '{node['ip']}' is not a valid IPv4 address.")
    if not node.get("ansible_user"):
        errors.append("ansible_user is required.")
    try:
        port = int(node.get("ssh_port", 22))
        if not (1 <= port <= 65535):
            raise ValueError
    except ValueError:
        errors.append("ssh_port must be a number between 1 and 65535.")
    return errors

