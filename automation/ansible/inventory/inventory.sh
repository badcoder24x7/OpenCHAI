#!/bin/bash
# inventory.sh — Thin wrapper so Ansible's inventory= config still works.
# Drop-in replacement for the old inventory.sh.
#
# Usage (set in ansible.cfg):
#   inventory = /opt/OpenCHAI/automation/ansible/inventory/inventory.sh
#
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INVENTORY_SCRIPT="${BASE_DIR}/inventory.py"
INVENTORY_FILE="${BASE_DIR}/inventory/inventory_def.txt"

exec python3 "$INVENTORY_SCRIPT" \
    --input-file "$INVENTORY_FILE" \
    "$@"
