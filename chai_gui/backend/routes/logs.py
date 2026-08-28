"""
OpenCHAI GUI - Logs Routes
GET  /logs/stream/{job_id}  — REST polling endpoint (last N lines)
WS   /logs/ws/{job_id}      — WebSocket streaming endpoint
GET  /logs/jobs             — list job log summaries
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query

from services.ansible_runner import (
    get_job,
    list_jobs,
    register_ws_callback,
    unregister_ws_callback,
    _jobs as _raw_jobs,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/stream/{job_id}", summary="Poll last N log lines for a job")
async def stream_logs(job_id: str, lines: int = Query(default=100, ge=1, le=10000)):
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    log_lines = job.get("log_lines", [])
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "lines": log_lines[-lines:],
        "total_lines": len(log_lines),
    }


@router.websocket("/ws/{job_id}")
async def ws_logs(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint — streams live Ansible output to the browser.

    Protocol
    ────────
    1. Replay already-buffered lines (late-joining clients see all output).
    2. If job already finished, send __done__:<status> and close.
    3. Otherwise register a live callback queue and stream lines in real time.
       A '__done__:<status>' sentinel from ansible_runner signals completion.
    4. Send '__ping__' keep-alive every 30 s to prevent idle timeouts.
    """
    await websocket.accept()
    logger.info("WS client connected for job %s", job_id)

    # Use the raw internal record for replay — it has the live-updated log_lines list.
    raw_job = _raw_jobs.get(job_id)
    if raw_job is None:
        await websocket.send_text(f"ERROR: job '{job_id}' not found")
        await websocket.close()
        return

    # ── Replay buffered lines ─────────────────────────────────────────────────
    buffered = list(raw_job.get("log_lines", []))
    for line in buffered:
        try:
            await websocket.send_text(line)
        except WebSocketDisconnect:
            return

    # ── Already finished — close after replay ────────────────────────────────
    if raw_job.get("status") not in ("running", None):
        try:
            await websocket.send_text(f"__done__:{raw_job['status']}")
        except WebSocketDisconnect:
            pass
        await websocket.close()
        return

    # ── Live streaming ────────────────────────────────────────────────────────
    queue: asyncio.Queue = asyncio.Queue()

    async def cb(line: str) -> None:
        await queue.put(line)

    register_ws_callback(job_id, cb)
    try:
        while True:
            try:
                line = await asyncio.wait_for(queue.get(), timeout=30.0)

                # Sentinel emitted by ansible_runner after process exits
                if line.startswith("__done__:"):
                    try:
                        await websocket.send_text(line)
                    except WebSocketDisconnect:
                        pass
                    break

                await websocket.send_text(line)

            except asyncio.TimeoutError:
                try:
                    await websocket.send_text("__ping__")
                except WebSocketDisconnect:
                    break

            # Safety fallback: job finished externally (e.g. cancel)
            if raw_job.get("status") not in ("running", None):
                status = raw_job.get("status", "unknown")
                try:
                    await websocket.send_text(f"__done__:{status}")
                except WebSocketDisconnect:
                    pass
                break

    except WebSocketDisconnect:
        logger.info("WS client disconnected from job %s", job_id)
    finally:
        unregister_ws_callback(job_id, cb)
        logger.info("WS session for job %s closed", job_id)


@router.get("/jobs", summary="List all job log summaries")
async def list_job_logs():
    jobs = list_jobs()
    return [
        {
            "job_id": j["job_id"],
            "playbook": j["playbook"],
            "status": j["status"],
            "started_at": j["started_at"],
            "finished_at": j["finished_at"],
            "line_count": len(j.get("log_lines", [])),
        }
        for j in jobs
    ]
