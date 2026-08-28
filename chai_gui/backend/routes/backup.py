"""
OpenCHAI GUI - Backup Routes
GET    /backup/list              — list all backups (optionally filter by file)
POST   /backup/restore           — restore a backup to its original location
DELETE /backup/delete            — delete a specific backup file
GET    /backup/read/{backup_path} — read backup file content
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.backup_service import (
    list_backups,
    restore_backup,
    delete_backup,
)

router = APIRouter()


class RestoreRequest(BaseModel):
    backup_path: str


class DeleteRequest(BaseModel):
    backup_path: str


@router.get("/list", summary="List all backup entries")
async def get_backups(file_path: Optional[str] = Query(None)):
    return list_backups(file_path)


@router.post("/restore", summary="Restore a backup file to its original location")
async def do_restore(req: RestoreRequest):
    try:
        pre = restore_backup(req.backup_path)
        return {
            "message": "Backup restored successfully.",
            "backup_path": req.backup_path,
            "pre_restore_backup": pre,
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete", summary="Delete a specific backup file")
async def do_delete(req: DeleteRequest):
    try:
        delete_backup(req.backup_path)
        return {"message": "Backup deleted.", "backup_path": req.backup_path}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/read", summary="Read content of a backup file")
async def read_backup(backup_path: str = Query(...)):
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail=f"Backup not found: {backup_path}")
    try:
        with open(backup_path) as fh:
            content = fh.read()
        return {"backup_path": backup_path, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
