"""
OpenCHAI GUI — Node Health Route  (v3)

Fixes vs v2
───────────
- Used hardcoded "root" / "~/.ssh/id_rsa" instead of settings values → fixed
- state_manager.nodes accessed as property (state_manager.state.nodes in v2)
- 404 returned as proper HTTPException, not a plain dict
- Single-node lookup does not run check_all_nodes on the full list
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from config import settings
from services.node_health import check_node, check_all_nodes
from services.state_manager import state_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", summary="Health check for all nodes")
async def get_all_nodes_health():
    nodes = state_manager.nodes
    if not nodes:
        return {"nodes": [], "total": 0}
    results = await check_all_nodes(
        nodes=nodes,
        ansible_user=settings.ANSIBLE_USER,
        ssh_key=settings.ANSIBLE_PRIVATE_KEY,
    )
    healthy   = sum(1 for r in results if r["status"] == "healthy")
    degraded  = sum(1 for r in results if r["status"] == "degraded")
    unreachable = sum(1 for r in results if r["status"] == "unreachable")
    return {
        "nodes":      results,
        "total":      len(results),
        "healthy":    healthy,
        "degraded":   degraded,
        "unreachable": unreachable,
    }


@router.get("/{node_id}", summary="Health check for a single node")
async def get_node_health(node_id: str):
    nodes = state_manager.nodes
    node = next((n for n in nodes if n.id == node_id), None)
    if node is None:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")

    result = await check_node(
        node_id=node.id,
        ip=node.ip_address,
        ansible_user=settings.ANSIBLE_USER,
        ssh_key=settings.ANSIBLE_PRIVATE_KEY,
    )
    return result
