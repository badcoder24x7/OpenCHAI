"""
OpenCHAI GUI - Inventory Def Routes  (v7 — routed through the real
automation/ansible/inventory.py via services/inventory_cli_bridge.py)

GET    /inventory-def            — list all nodes (password shown as set/none only)
POST   /inventory-def/add        — add a node (password, if given, is vault-encrypted)
PUT    /inventory-def/{hostname} — update a node (password, if given, is vault-encrypted)
DELETE /inventory-def/{hostname} — delete a node (also deletes its host_vars file)
POST   /inventory-def/bulk       — bulk import (7-field text: node ip user group hostname ssh_port password)
GET    /inventory-def/raw        — raw content of inventory_def.txt (no secrets — never contains passwords)
POST   /inventory-def/ssh-test   — test SSH connectivity to a node

Why this now shells into automation/ansible/inventory.py instead of having
its own read/write/vault logic
────────────────────────────────────────────────────────────────────────────
That real script is the single source of truth the rest of the automation
tree (inventory.sh's dynamic inventory, bootstrap_import.py, every
playbook run) already depends on: node passwords live in one encrypted
automation/ansible/inventory/group_vars/all/vault.yml, and every
host_vars/<node>.yml is just a stub referencing it. The GUI previously
maintained a second, incompatible password-storage scheme; whichever one
last touched host_vars/ would silently break the other's credentials. See
services/inventory_cli_bridge.py's module docstring for the full story.

ansible_become_pass note: the real vault only stores ONE secret per node
(used for both SSH login and sudo/become — see the host_vars stub, which
references the same vault_passwords[...] value for both keys). If a
caller supplies a different ansible_become_pass than ansible_password,
we honor ansible_password as authoritative and log the discrepancy,
since the underlying automation has no way to store two.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services import inventory_cli_bridge as inv

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class InventoryNode(BaseModel):
    ansible_hostname:    str           = Field(...,  example="cn01")
    ip:                  str           = Field(...,  example="192.168.1.101")
    ansible_user:        str           = Field("root", example="root")
    ansible_password:    str           = Field("",   example="secret")
    ansible_become_pass: str           = Field("",   example="")
    group:               str           = Field("compute", example="compute")
    hostname:            Optional[str] = Field(None, example="cn01.cluster.local")
    ssh_port:            str           = Field("22", example="22")


class NodeUpdate(BaseModel):
    ip:                  Optional[str] = None
    ansible_user:        Optional[str] = None
    ansible_password:    Optional[str] = None   # None=unchanged, ""=clear, else=set
    ansible_become_pass: Optional[str] = None
    group:                Optional[str] = None
    hostname:             Optional[str] = None
    ssh_port:             Optional[str] = None


class BulkImportRequest(BaseModel):
    text: str   # 7-field lines: node ip user group hostname ssh_port password
    backup: bool = True


class SshTestRequest(BaseModel):
    ansible_hostname: Optional[str] = None   # preferred: resolves ip/user/port/password from inventory
    ip:       Optional[str] = None
    user:     Optional[str] = None
    port:     Optional[int] = None
    password: Optional[str] = None
    key_path: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", summary="List all inventory nodes")
async def list_nodes() -> List[Dict]:
    try:
        return inv.list_nodes()
    except inv.BridgeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add", summary="Add a node (password, if given, is vault-encrypted via the real automation script)")
async def add(node_in: InventoryNode, backup: bool = True):
    if node_in.ansible_become_pass and node_in.ansible_become_pass != node_in.ansible_password:
        logger.warning(
            "Node '%s': ansible_become_pass differs from ansible_password — "
            "the automation vault stores one shared credential per node; "
            "ansible_password is being used for both.",
            node_in.ansible_hostname,
        )
    try:
        total = inv.add_node(
            node=node_in.ansible_hostname,
            ip=node_in.ip,
            user=node_in.ansible_user,
            group=node_in.group,
            hostname=node_in.hostname or node_in.ansible_hostname,
            ssh_port=node_in.ssh_port,
            password=node_in.ansible_password,
            backup=backup,
        )
    except inv.BridgeError as e:
        msg = str(e)
        status = 409 if "already exists" in msg or "already assigned" in msg else 422
        raise HTTPException(status_code=status, detail=msg)

    return {"message": f"Node '{node_in.ansible_hostname}' added.", "total": total}


@router.put("/{ansible_hostname}", summary="Update a node (password, if given, is vault-encrypted)")
async def update(ansible_hostname: str, updates: NodeUpdate, backup: bool = True):
    raw = updates.model_dump()
    if raw.get("ansible_become_pass") not in (None, "") and raw.get("ansible_become_pass") != raw.get("ansible_password"):
        logger.warning(
            "Node '%s': ansible_become_pass differs from ansible_password — "
            "using ansible_password for the shared vault credential.",
            ansible_hostname,
        )

    if all(v is None for v in raw.values()):
        raise HTTPException(status_code=400, detail="No fields to update.")

    try:
        total = inv.update_node(
            ansible_hostname,
            ip=raw.get("ip"),
            user=raw.get("ansible_user"),
            group=raw.get("group"),
            hostname=raw.get("hostname"),
            ssh_port=raw.get("ssh_port"),
            password=raw.get("ansible_password"),
            backup=backup,
        )
    except inv.BridgeError as e:
        msg = str(e)
        status = 404 if "not found" in msg else 422
        raise HTTPException(status_code=status, detail=msg)

    return {"message": f"Node '{ansible_hostname}' updated.", "total": total}


@router.delete("/{ansible_hostname}", summary="Delete a node (and its vault entry / host_vars file)")
async def delete(ansible_hostname: str, backup: bool = True):
    try:
        total = inv.delete_node(ansible_hostname, backup=backup)
    except inv.BridgeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {"message": f"Node '{ansible_hostname}' deleted.", "total": total}


@router.post("/bulk", summary="Bulk import nodes — 7-field lines: node ip user group hostname ssh_port password")
async def bulk(req: BulkImportRequest):
    try:
        result = inv.bulk_import(req.text, backup=req.backup)
    except inv.BridgeError as e:
        raise HTTPException(status_code=422, detail=str(e))

    added, skipped, total = result["added"], result["skipped"], result["total"]

    if added and not skipped:
        message = f"Imported {added} node(s). Total nodes: {total}."
    elif added and skipped:
        message = f"Imported {added} node(s), skipped {len(skipped)} — see details. Total nodes: {total}."
    elif not added and skipped:
        message = f"Imported 0 nodes — all {len(skipped)} row(s) were skipped. See details."
    else:
        message = "No rows found in the pasted/uploaded file."

    return {"message": message, "total": total, "added": added, "skipped": skipped}


@router.get("/raw", summary="Raw content of inventory_def.txt")
async def raw_file():
    try:
        content = inv.raw_file_content()
        path = inv.inventory_file_path()
    except inv.BridgeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": path, "content": content}


def _ssh_test_password(ip: str, user: str, port: int, password: str) -> Dict:
    """Real password-auth connectivity test via paramiko. Runs in a thread
    since paramiko is blocking. This is what makes SSH test actually work
    for nodes whose only credential is the vault-stored password — a key-only
    `ssh` client (BatchMode=yes) can never succeed for those."""
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(ip, port=port, username=user, password=password,
                        timeout=8, banner_timeout=8, auth_timeout=8, look_for_keys=False, allow_agent=False)
        return {"success": True, "ip": ip, "user": user, "port": port, "message": "SSH connection successful."}
    except paramiko.AuthenticationException:
        return {"success": False, "ip": ip, "user": user, "port": port, "message": "Authentication failed — wrong password or user."}
    except Exception as e:
        return {"success": False, "ip": ip, "user": user, "port": port, "message": str(e)}
    finally:
        client.close()


async def _ssh_test_key(ip: str, user: str, port: int, key_path: Optional[str]) -> Dict:
    """Key-based fallback for nodes with no stored password (e.g. key-only auth)."""
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes", "-p", str(port)]
    if key_path:
        cmd += ["-i", key_path]
    cmd += [f"{user}@{ip}", "echo OPENCHAI_SSH_OK"]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        success = proc.returncode == 0 and b"OPENCHAI_SSH_OK" in stdout
        return {
            "success": success, "ip": ip, "user": user, "port": port,
            "message": "SSH connection successful." if success else stderr.decode().strip() or "No key-based access and no stored password for this node.",
        }
    except asyncio.TimeoutError:
        return {"success": False, "ip": ip, "message": "Connection timed out."}
    except Exception as e:
        return {"success": False, "ip": ip, "message": str(e)}


@router.post("/ssh-test", summary="Test SSH connectivity to a node")
async def ssh_test(req: SshTestRequest):
    """Tests connectivity using whatever credential the node actually has:
    the vault-stored password when one is set (the common case for nodes
    added through this UI), otherwise falls back to key-based auth."""
    ip, user, port, password = req.ip, req.user, req.port, req.password

    if req.ansible_hostname:
        try:
            info = inv.get_connection_info(req.ansible_hostname)
        except inv.BridgeError as e:
            raise HTTPException(status_code=404, detail=str(e))
        ip = ip or info["ip"]
        user = user or info["user"]
        port = port or info["port"]
        password = password or info["password"]

    if not ip:
        raise HTTPException(status_code=422, detail="Provide either ansible_hostname or ip.")
    user, port = user or "root", port or 22

    if password:
        return await asyncio.to_thread(_ssh_test_password, ip, user, port, password)
    return await _ssh_test_key(ip, user, port, req.key_path)
