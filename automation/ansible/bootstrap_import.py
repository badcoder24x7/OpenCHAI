#!/usr/bin/env python3
"""
bootstrap_import.py — One-time bootstrap importer
===================================================
Replaces the old shell CSV loop that called ansible_vault.sh per host.

Usage:
    python3 bootstrap_import.py nodes.txt
    python3 bootstrap_import.py nodes.csv   # comma-separated variant

Input format (space or comma separated, one host per line):
    <node> <ip> <user> <group> <hostname> <ssh_port> <password>

The script:
  1. Parses all 7 fields
  2. Writes the 6-field inventory_def.txt (no passwords)
  3. Syncs all passwords into the encrypted Ansible Vault file
  4. Generates per-host host_vars stubs referencing vault variables
  5. DELETES the source file (unless --no-delete is passed)

This is the safe migration path from the old ansible_vault.sh approach.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent))

from inventory import (
    InventoryManager,
    CONFIG,
    setup_logging,
    log,
)


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Bootstrap inventory from 7-field definition file")
    p.add_argument("def_file", help="7-field definition file path")
    p.add_argument("--no-delete", action="store_true",
                   help="Keep the definition file (INSECURE — plaintext passwords remain on disk)")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    setup_logging(CONFIG["log_file"], debug=args.debug)

    src = Path(args.def_file)
    if not src.exists():
        print(f"Error: file not found: {src}", file=sys.stderr)
        return 1

    manager = InventoryManager(CONFIG)

    try:
        count, _ = manager.import_definition_file(src)
        print(f"✓ Imported {count} host(s).")
        print(f"  Inventory : {CONFIG['inventory_file']}")
        print(f"  Vault     : {CONFIG['vault_file']}")
        print(f"  Host vars : {CONFIG['host_vars_dir']}/")

        if not args.no_delete:
            src.unlink()
            print(f"✓ Source file deleted: {src}")
        else:
            print(f"\n  ⚠  WARNING: {src} still exists and contains plaintext passwords.")
            print("     Delete it immediately: rm -f " + str(src))

    except Exception as exc:
        log.error("%s: %s", type(exc).__name__, exc)
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
