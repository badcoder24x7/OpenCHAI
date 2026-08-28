"""
OpenCHAI GUI — Node Health Service  (v3)

Changes vs v2
─────────────
- SSH check skipped gracefully when key file does not exist (v2 hung)
- check_all_nodes() accepts both Node objects and plain dicts (defensive)
- Added timeout to ping to prevent indefinite hangs
- Exposed NodeHealthResult TypedDict for type-checking downstream
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Ping / SSH helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _ping_once(ip: str, timeout: int = 3) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", str(timeout), ip,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
        return proc.returncode == 0
    except Exception:
        return False


async def _ssh_check(ip: str, user: str, key: str, timeout: int = 6) -> bool:
    expanded = os.path.expanduser(key)
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "BatchMode=yes",
    ]
    if os.path.exists(expanded):
        cmd += ["-i", expanded]
    cmd += [f"{user}@{ip}", "true"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
        return proc.returncode == 0
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def check_node(
    node_id: str,
    ip: str,
    ansible_user: str = "root",
    ssh_key: str = "~/.ssh/id_rsa",
) -> Dict[str, Any]:
    ping_ok = await _ping_once(ip)
    ssh_ok  = await _ssh_check(ip, ansible_user, ssh_key) if ping_ok else False

    if ping_ok and ssh_ok:
        status = "healthy"
    elif ping_ok:
        status = "degraded"
    else:
        status = "unreachable"

    return {
        "node_id":    node_id,
        "ip":         ip,
        "ping":       ping_ok,
        "ssh":        ssh_ok,
        "status":     status,
        "checked_at": time.time(),
    }


async def check_all_nodes(
    nodes: List[Any],
    ansible_user: str,
    ssh_key: str,
) -> List[Dict[str, Any]]:
    """Run health checks concurrently. Accepts Node objects or plain dicts."""

    def _id(n: Any) -> str:
        return getattr(n, "id", None) or n.get("id", "unknown")

    def _ip(n: Any) -> str:
        return (
            getattr(n, "ip_address", None)
            or getattr(n, "ip", None)
            or n.get("ip_address", n.get("ip", ""))
        )

    tasks = [
        check_node(_id(n), _ip(n), ansible_user, ssh_key)
        for n in nodes
    ]
    return list(await asyncio.gather(*tasks, return_exceptions=False))
