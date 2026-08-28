"""
OpenCHAI GUI - Enhanced Playbooks Routes
Dynamic category scanning + per-playbook variable extraction for form generation.

GET  /playbooks                         — flat list (legacy compat)
GET  /playbooks/categories              — list all categories (dirs)
GET  /playbooks/categories/{cat}        — playbooks inside a category
GET  /playbooks/detail/{cat}/{name}     — parsed playbook: vars + form fields
GET  /playbooks/inventory-groups        — groups/hostnames from inventory_def.txt
POST /playbooks/execute                 — run a playbook with user-supplied vars
GET  /playbooks/tree                    — full tree
"""

from __future__ import annotations
import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.playbook_parser import (
    list_categories,
    list_playbooks_in_category,
    get_playbook_detail,
)
from services.ansible_runner import run_playbook
from services.inventory_def_service import read_inventory_def
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


class ExecuteRequest(BaseModel):
    playbook_rel_path: str
    extra_vars:        Optional[Dict[str, Any]] = None
    limit:             Optional[str] = None
    tags:              Optional[List[str]] = None
    dry_run:           bool = False
    verbosity:         int  = 0
    vault_password:    Optional[str] = None


@router.get("", summary="Flat list of all playbooks (legacy)")
async def list_all():
    base = settings.PLAYBOOK_LIBRARY
    results = []
    if not base or not os.path.isdir(base):
        return results
    for root, _dirs, files in os.walk(base):
        for fname in sorted(files):
            if fname.endswith((".yml", ".yaml")):
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, base)
                cat  = os.path.dirname(rel) or "root"
                results.append({"name": fname, "path": rel, "category": cat, "full_path": full})
    return results


@router.get("/categories", summary="List all playbook categories (directories)")
async def get_categories():
    cats = list_categories()
    return {"categories": cats, "total": len(cats)}


@router.get("/categories/{category}", summary="List playbooks inside a category")
async def get_category_playbooks(category: str):
    pbs = list_playbooks_in_category(category)
    return {"category": category, "playbooks": pbs, "total": len(pbs)}


@router.get("/inventory-groups", summary="Groups and hostnames from inventory_def.txt")
async def get_groups():
    nodes = read_inventory_def()
    groups    = sorted({n.get("group", "compute") for n in nodes if n.get("group")})
    hostnames = sorted({n["ansible_hostname"] for n in nodes})
    return {"groups": groups, "hostnames": hostnames}


@router.get("/detail/{category}/{playbook_name:path}", summary="Parse playbook vars and return form fields")
async def get_detail(category: str, playbook_name: str):
    try:
        return get_playbook_detail(category, playbook_name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute", summary="Execute a playbook with dynamic vars")
async def execute_playbook(req: ExecuteRequest):
    if not settings.PLAYBOOK_LIBRARY:
        raise HTTPException(status_code=500, detail="PLAYBOOK_LIBRARY not configured.")

    playbook_full = os.path.join(settings.PLAYBOOK_LIBRARY, req.playbook_rel_path)
    if not os.path.exists(playbook_full):
        raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_full}")

    inventory = os.path.join(settings.ANSIBLE_DIR, "inventory", "inventory_def.txt")
    if not os.path.exists(inventory):
        inventory = settings.INVENTORY_PATH

    job_id = await run_playbook(
        playbook_path=playbook_full,
        inventory_path=inventory,
        ansible_cfg=settings.ANSIBLE_CFG,
        extra_vars=dict(req.extra_vars) if req.extra_vars else None,
        tags=req.tags,
        limit=req.limit,
        dry_run=req.dry_run,
        ansible_user=settings.ANSIBLE_USER,
        ssh_key=settings.ANSIBLE_PRIVATE_KEY,
        vault_password=req.vault_password,
    )
    return {
        "job_id":  job_id,
        "status":  "running",
        "playbook": req.playbook_rel_path,
        "dry_run": req.dry_run,
        "limit":   req.limit,
        "message": f"Job started. Stream logs at /logs/ws/{job_id}",
    }


@router.get("/tree", summary="Full playbook library tree")
async def playbook_tree():
    base = settings.PLAYBOOK_LIBRARY
    tree: Dict[str, Any] = {}
    if not base or not os.path.isdir(base):
        return {"error": f"Playbook library not found at {base}"}
    for root, dirs, files in os.walk(base):
        dirs.sort()
        rel = os.path.relpath(root, base)
        node = tree
        if rel != ".":
            for part in rel.split(os.sep):
                node = node.setdefault(part, {})
        node["_files"] = sorted(f for f in files if f.endswith((".yml", ".yaml")))
    return tree
