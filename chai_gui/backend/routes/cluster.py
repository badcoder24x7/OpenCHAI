"""
OpenCHAI GUI - Cluster Routes
POST /cluster/create   — save cluster config
GET  /cluster          — fetch current config
GET  /cluster/preview  — YAML preview of group_vars
DELETE /cluster        — reset all state
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from models import ClusterConfig, ClusterState
from services.config_mapper import generate_group_vars, render_yaml_preview
from services.inventory_generator import generate_inventory
from services.state_manager import state_manager
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/create", summary="Create or update cluster configuration")
async def create_cluster(config: ClusterConfig):
    state = state_manager.state
    state.config = config
    # Re-generate inventory and group_vars whenever config changes
    if state.nodes:
        try:
            generate_inventory(state.nodes, config, settings.INVENTORY_PATH)
            generate_group_vars(config, settings.GROUP_VARS_DIR)
        except Exception as exc:
            logger.error("Failed to (re)generate inventory: %s", exc)
    state_manager.save()
    return {"message": "Cluster configuration saved.", "cluster_name": config.cluster_name}


@router.get("", summary="Get current cluster configuration")
async def get_cluster():
    state = state_manager.state
    if state.config is None:
        raise HTTPException(status_code=404, detail="No cluster configuration found.")
    return state.config


@router.get("/preview", summary="YAML preview of group_vars/all.yml")
async def yaml_preview():
    state = state_manager.state
    if state.config is None:
        raise HTTPException(status_code=404, detail="No cluster configuration found.")
    yaml_content = render_yaml_preview(state.config)
    return {"yaml": yaml_content}


@router.get("/state", summary="Full cluster state (config + nodes + status)")
async def get_state():
    return state_manager.state


@router.delete("", summary="Reset all cluster state")
async def reset_cluster():
    state_manager.reset()
    return {"message": "Cluster state reset."}
