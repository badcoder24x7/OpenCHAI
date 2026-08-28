"""
OpenCHAI GUI - Node Routes
POST   /nodes/add         — add a node
GET    /nodes             — list all nodes
GET    /nodes/{node_id}   — get single node
PUT    /nodes/{node_id}   — update node
DELETE /nodes/{node_id}   — delete node
POST   /nodes/bulk        — bulk import nodes from list
"""

from __future__ import annotations

import logging
import uuid
from typing import List

from fastapi import APIRouter, HTTPException

from models import Node, NodeCreate, NodeUpdate
from services.inventory_generator import generate_inventory
from services.state_manager import state_manager
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _regen_inventory():
    state = state_manager.state
    if state.config and state.nodes:
        try:
            generate_inventory(state.nodes, state.config, settings.INVENTORY_PATH)
        except Exception as exc:
            logger.error("Inventory regeneration failed: %s", exc)


@router.post("/add", summary="Add a node to the cluster")
async def add_node(node_in: NodeCreate) -> Node:
    state = state_manager.state
    # Hostname uniqueness check
    existing = [n for n in state.nodes if n.hostname == node_in.hostname]
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Node with hostname '{node_in.hostname}' already exists.",
        )
    node = Node(id=str(uuid.uuid4()), **node_in.model_dump())
    state.nodes.append(node)
    state_manager.save()
    _regen_inventory()
    return node


@router.get("", summary="List all nodes")
async def list_nodes() -> List[Node]:
    return state_manager.state.nodes


@router.get("/{node_id}", summary="Get a specific node")
async def get_node(node_id: str) -> Node:
    node = _find(node_id)
    return node


@router.put("/{node_id}", summary="Update a node")
async def update_node(node_id: str, updates: NodeUpdate) -> Node:
    state = state_manager.state
    node = _find(node_id)
    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(node, field, value)
    state_manager.save()
    _regen_inventory()
    return node


@router.delete("/{node_id}", summary="Delete a node")
async def delete_node(node_id: str):
    state = state_manager.state
    node = _find(node_id)
    state.nodes = [n for n in state.nodes if n.id != node_id]
    state_manager.save()
    _regen_inventory()
    return {"message": f"Node '{node.hostname}' deleted."}


@router.post("/bulk", summary="Bulk import nodes")
async def bulk_import(nodes_in: List[NodeCreate]) -> List[Node]:
    state = state_manager.state
    added: List[Node] = []
    for node_in in nodes_in:
        if any(n.hostname == node_in.hostname for n in state.nodes):
            continue  # skip duplicates silently
        node = Node(id=str(uuid.uuid4()), **node_in.model_dump())
        state.nodes.append(node)
        added.append(node)
    state_manager.save()
    _regen_inventory()
    return added


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find(node_id: str) -> Node:
    state = state_manager.state
    for node in state.nodes:
        if node.id == node_id:
            return node
    raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found.")
