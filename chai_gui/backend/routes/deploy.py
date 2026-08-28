"""
OpenCHAI GUI - Deploy Routes
POST /deploy/start          — launch playbook
GET  /deploy/jobs           — list all jobs
GET  /deploy/jobs/{job_id}  — get job status
POST /deploy/generate       — generate inventory + group_vars only (no run)
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from models import DeployRequest, DeployResponse, DeploymentStatus
from services.ansible_runner import get_job, list_jobs, run_playbook
from services.config_mapper import generate_group_vars
from services.inventory_generator import generate_inventory
from services.state_manager import state_manager
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/start", summary="Start a deployment (run an Ansible playbook)")
async def start_deploy(req: DeployRequest) -> DeployResponse:
    state = state_manager.state

    if state.config is None:
        raise HTTPException(status_code=400, detail="No cluster configuration. Create one first.")
    if not state.nodes:
        raise HTTPException(status_code=400, detail="No nodes defined. Add nodes first.")

    # Always regenerate inventory + group_vars before deploying
    try:
        generate_inventory(state.nodes, state.config, settings.INVENTORY_PATH)
        generate_group_vars(state.config, settings.GROUP_VARS_DIR)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Inventory generation failed: {exc}")

    # Resolve playbook path relative to playbook_library if not absolute
    playbook = req.playbook
    if not os.path.isabs(playbook):
        playbook = os.path.join(settings.PLAYBOOK_LIBRARY, playbook)

    if not os.path.exists(playbook):
        # In dev mode / demo, allow non-existent playbooks with a warning
        logger.warning("Playbook not found at %s — running in demo mode", playbook)

    job_id = await run_playbook(
        playbook_path=playbook,
        inventory_path=settings.INVENTORY_PATH,
        ansible_cfg=settings.ANSIBLE_CFG,
        extra_vars=req.extra_vars,
        tags=req.tags,
        limit=req.limit,
        dry_run=req.dry_run,
        ansible_user=state.config.ansible_user,
        ssh_key=state.config.ansible_ssh_key,
        vault_password=req.vault_password,
    )

    state.deployment_status = DeploymentStatus.running
    state_manager.save()

    return DeployResponse(
        job_id=job_id,
        status=DeploymentStatus.running,
        message="Deployment started. Connect to /logs/ws/{job_id} for live output.",
        playbook=req.playbook,
        dry_run=req.dry_run,
    )


@router.post("/generate", summary="Generate Ansible configs without running playbook")
async def generate_only():
    state = state_manager.state
    if state.config is None:
        raise HTTPException(status_code=400, detail="No cluster configuration.")

    inv_content = generate_inventory(
        state.nodes, state.config, settings.INVENTORY_PATH
    )
    gv_files = generate_group_vars(state.config, settings.GROUP_VARS_DIR)

    return {
        "message": "Inventory and group_vars generated.",
        "inventory": inv_content,
        "group_vars": gv_files,
    }


@router.get("/jobs", summary="List all deployment jobs")
async def get_jobs():
    return list_jobs()


@router.get("/jobs/{job_id}", summary="Get status of a specific job")
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job
