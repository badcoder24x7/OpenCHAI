"""
OpenCHAI GUI — Backup Service  (v3)

Changes vs v2
─────────────
- BACKUP_ROOT resolved lazily so it picks up runtime OPENCHAI_ROOT correctly
- delete_backup() uses os.path.commonpath for safe path-traversal check
  (os.path.abspath().startswith() is broken when paths share a prefix letter)
- restore_backup() validates backup_path is inside BACKUP_ROOT before reading
- list_backups() handles unreadable backup directories gracefully
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger(__name__)


def _backup_root() -> str:
    """Return backup root, resolved at call-time (settings may change at startup)."""
    return os.path.join(settings.OPENCHAI_ROOT, "backup") if settings.OPENCHAI_ROOT else ""


# ─────────────────────────────────────────────────────────────────────────────
# Core utility
# ─────────────────────────────────────────────────────────────────────────────

def backup_and_write(file_path: str, new_content: str, enabled: bool = True) -> Optional[str]:
    """
    Safely write *new_content* to *file_path*.

    1. If enabled and file exists → create timestamped backup first.
    2. Write via temp-file → os.replace (atomic on POSIX).
    Returns backup path or None.
    """
    file_path = os.path.abspath(file_path)
    backup_path: Optional[str] = None

    if enabled and os.path.exists(file_path):
        backup_path = _create_backup(file_path)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    dir_name = os.path.dirname(file_path)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".openchai_tmp_")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(new_content)
            os.replace(tmp_path, file_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as exc:
        logger.error("Atomic write failed for %s: %s", file_path, exc)
        raise

    logger.info("Written: %s  (backup: %s)", file_path, backup_path or "none")
    return backup_path


# ─────────────────────────────────────────────────────────────────────────────
# Listing / restore / delete
# ─────────────────────────────────────────────────────────────────────────────

def list_backups(file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    root = _backup_root()
    if not root or not os.path.isdir(root):
        return []

    results: List[Dict[str, Any]] = []
    for ts_dir in sorted(os.listdir(root), reverse=True):
        ts_full = os.path.join(root, ts_dir)
        if not os.path.isdir(ts_full):
            continue
        try:
            for dirpath, _, files in os.walk(ts_full):
                for fname in files:
                    bak_path = os.path.join(dirpath, fname)
                    rel = os.path.relpath(bak_path, ts_full)
                    original = (
                        os.path.join(settings.OPENCHAI_ROOT, rel)
                        if settings.OPENCHAI_ROOT
                        else rel
                    )
                    if file_path and os.path.abspath(file_path) != os.path.abspath(original):
                        continue
                    try:
                        stat = os.stat(bak_path)
                    except OSError:
                        continue
                    results.append({
                        "backup_path":   bak_path,
                        "original_path": original,
                        "timestamp":     ts_dir,
                        "size_bytes":    stat.st_size,
                        "relative_path": rel,
                    })
        except OSError as exc:
            logger.warning("Could not read backup dir %s: %s", ts_full, exc)

    return results


def restore_backup(backup_path: str) -> str:
    backup_path = os.path.abspath(backup_path)
    root = _backup_root()

    if not root:
        raise RuntimeError("OPENCHAI_ROOT not set — cannot determine backup root.")

    # Security: ensure path is inside backup root
    if os.path.commonpath([backup_path, os.path.abspath(root)]) != os.path.abspath(root):
        raise PermissionError(f"backup_path is outside backup directory: {backup_path}")

    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    rel = os.path.relpath(backup_path, root)
    parts = rel.split(os.sep, 1)
    if len(parts) < 2:
        raise ValueError(f"Cannot determine original path from: {backup_path}")

    original_path = os.path.join(settings.OPENCHAI_ROOT, parts[1])

    with open(backup_path) as fh:
        content = fh.read()

    pre_restore_bak = backup_and_write(original_path, content, enabled=True)
    logger.info("Restored %s → %s (pre-restore backup: %s)",
                backup_path, original_path, pre_restore_bak)
    return pre_restore_bak or ""


def delete_backup(backup_path: str) -> None:
    backup_path = os.path.abspath(backup_path)
    root = os.path.abspath(_backup_root())

    if not root:
        raise RuntimeError("OPENCHAI_ROOT not set.")

    if os.path.commonpath([backup_path, root]) != root:
        raise PermissionError("Path is outside backup directory.")

    if os.path.exists(backup_path):
        os.unlink(backup_path)
        # Remove empty parent timestamp dirs
        parent = os.path.dirname(backup_path)
        while parent != root and os.path.isdir(parent):
            if not os.listdir(parent):
                os.rmdir(parent)
                parent = os.path.dirname(parent)
            else:
                break


# ─────────────────────────────────────────────────────────────────────────────
# Internal
# ─────────────────────────────────────────────────────────────────────────────

def _create_backup(file_path: str) -> str:
    root = _backup_root()
    if not root:
        logger.warning("OPENCHAI_ROOT not set — backup skipped for %s", file_path)
        return ""

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    try:
        rel = os.path.relpath(file_path, settings.OPENCHAI_ROOT)
    except ValueError:
        rel = os.path.basename(file_path)

    backup_dest = os.path.join(root, ts, rel)
    os.makedirs(os.path.dirname(backup_dest), exist_ok=True)
    shutil.copy2(file_path, backup_dest)
    logger.info("Backup created: %s → %s", file_path, backup_dest)
    return backup_dest
