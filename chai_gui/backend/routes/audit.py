"""
MODULE: Audit Log Route + Service
PURPOSE: Append-only audit trail for all mutating API actions
INTEGRATION:
  1. Copy to backend/routes/audit.py
  2. In app.py add:
       from routes.audit import router as audit_router
       app.include_router(audit_router, prefix="/audit", tags=["Audit"])
  3. In any existing route, call audit_log.record(...) after a successful mutation.
DEPENDENCIES: stdlib only
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import List, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audit log file path (sits next to cluster_state.json)
# ---------------------------------------------------------------------------
AUDIT_FILE = os.path.join(settings.LOG_DIR, "audit.jsonl")


# ---------------------------------------------------------------------------
# Internal writer
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    ts: float
    action: str           # e.g. "node.add", "cluster.create", "deploy.start"
    actor: str = "system" # future: real user identity
    detail: Optional[dict] = None


def record(action: str, detail: dict | None = None, actor: str = "system") -> None:
    """Append one audit entry. Call this from any route handler."""
    entry = AuditEntry(ts=time.time(), action=action, actor=actor, detail=detail)
    try:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        with open(AUDIT_FILE, "a") as fh:
            fh.write(entry.model_dump_json() + "\n")
    except Exception as exc:
        logger.warning("Audit write failed: %s", exc)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", summary="List recent audit entries")
async def list_audit(
    limit: int = Query(100, ge=1, le=1000),
    action_filter: Optional[str] = Query(None, alias="action"),
):
    """Returns the most recent N audit log entries, newest-first."""
    if not os.path.exists(AUDIT_FILE):
        return {"entries": []}

    lines: List[str] = []
    with open(AUDIT_FILE) as fh:
        lines = fh.readlines()

    # Newest-first
    lines.reverse()

    entries = []
    for line in lines:
        try:
            obj = json.loads(line)
            if action_filter and not obj.get("action", "").startswith(action_filter):
                continue
            entries.append(obj)
            if len(entries) >= limit:
                break
        except Exception:
            pass

    return {"entries": entries, "total": len(entries)}


@router.delete("", summary="Clear all audit entries")
async def clear_audit():
    """Wipes the audit log. Intended for dev/testing only."""
    if os.path.exists(AUDIT_FILE):
        os.remove(AUDIT_FILE)
    return {"message": "Audit log cleared"}
