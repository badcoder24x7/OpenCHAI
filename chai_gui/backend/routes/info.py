"""
OpenCHAI GUI - Info / Directory Routes
GET /info/paths      — all resolved OpenCHAI paths
GET /info/tree       — top-level directory listing of OPENCHAI_ROOT
GET /info/ansible    — ansible directory structure
"""

from __future__ import annotations
import os
from typing import Any, Dict, List
from fastapi import APIRouter
from config import settings

router = APIRouter()


@router.get("/paths", summary="All resolved OpenCHAI directory paths")
async def get_paths():
    def check(path: str) -> Dict[str, Any]:
        return {"path": path, "exists": os.path.exists(path)}

    return {
        "openchai_root":    check(settings.OPENCHAI_ROOT),
        "ansible_dir":      check(settings.ANSIBLE_DIR),
        "playbook_library": check(settings.PLAYBOOK_LIBRARY),
        "inventory_path":   check(settings.INVENTORY_PATH),
        "group_vars_dir":   check(settings.GROUP_VARS_DIR),
        "ansible_cfg":      check(settings.ANSIBLE_CFG),
        "subdirs": {
            "ai":           check(settings.AI_DIR),
            "benchmarks":   check(settings.BENCHMARKS_DIR),
            "chai_cli":     check(settings.CHAI_CLI_DIR),
            "chai_setup":   check(settings.CHAI_SETUP_DIR),
            "container":    check(settings.CONTAINER_DIR),
            "docs":         check(settings.DOCS_DIR),
            "headnode":     check(settings.HEADNODE_DIR),
            "hpc":          check(settings.HPC_DIR),
            "images":       check(settings.IMAGES_DIR),
            "logs":         check(settings.LOGS_DIR_ROOT),
            "monitoring":   check(settings.MONITORING_DIR),
            "networking":   check(settings.NETWORKING_DIR),
            "policies":     check(settings.POLICIES_DIR),
            "provisioning": check(settings.PROVISIONING_DIR),
            "releases":     check(settings.RELEASES_DIR),
            "servicenodes": check(settings.SERVICENODES_DIR),
            "storage":      check(settings.STORAGE_DIR),
        },
    }


@router.get("/tree", summary="Top-level directory listing of OpenCHAI root")
async def get_tree():
    root = settings.OPENCHAI_ROOT
    if not os.path.isdir(root):
        return {"error": f"OPENCHAI_ROOT not found: {root}"}

    entries = []
    for name in sorted(os.listdir(root)):
        full = os.path.join(root, name)
        entries.append({
            "name": name,
            "type": "dir" if os.path.isdir(full) else "file",
            "path": full,
        })
    return {"root": root, "entries": entries}


@router.get("/ansible", summary="Ansible directory structure")
async def get_ansible_tree():
    base = settings.ANSIBLE_DIR
    if not os.path.isdir(base):
        return {"error": f"Ansible dir not found: {base}"}

    result: Dict[str, Any] = {"path": base, "children": {}}

    for root, dirs, files in os.walk(base):
        dirs.sort()
        rel = os.path.relpath(root, base)
        node = result["children"]
        if rel != ".":
            for part in rel.split(os.sep):
                node = node.setdefault(part, {})
        node["_files"] = sorted(files)

    return result
