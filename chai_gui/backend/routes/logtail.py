"""
MODULE: WebSocket Live Log Tail Route
PURPOSE: Stream any backend log file in real-time via WebSocket
INTEGRATION:
  1. Copy to backend/routes/logtail.py
  2. In app.py:
       from routes.logtail import router as logtail_router
       app.include_router(logtail_router, prefix="/logtail", tags=["Log Tail"])
DEPENDENCIES: stdlib only
"""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# Allowed log file aliases (security: never allow arbitrary paths)
ALLOWED_LOGS = {
    "app":   os.path.join(settings.LOG_DIR, "openchai_gui.log"),
    "audit": os.path.join(settings.LOG_DIR, "audit.jsonl"),
}


@router.websocket("/{log_name}")
async def tail_log(websocket: WebSocket, log_name: str, lines: int = 50):
    """
    WebSocket endpoint: streams new lines appended to a named log.

    Connect with: ws://<host>/logtail/{log_name}?lines=50
    Allowed names: 'app', 'audit'
    """
    if log_name not in ALLOWED_LOGS:
        await websocket.close(code=4004, reason=f"Unknown log: {log_name!r}")
        return

    await websocket.accept()
    log_path = ALLOWED_LOGS[log_name]

    async def send_tail():
        """Send last N lines on connect."""
        if not os.path.exists(log_path):
            await websocket.send_text("[Log file not yet created]\n")
            return
        with open(log_path) as fh:
            all_lines = fh.readlines()
        for line in all_lines[-lines:]:
            await websocket.send_text(line)

    try:
        await send_tail()

        # Follow file: poll for new content
        file_pos = os.path.getsize(log_path) if os.path.exists(log_path) else 0

        while True:
            await asyncio.sleep(0.5)
            if not os.path.exists(log_path):
                continue
            current_size = os.path.getsize(log_path)
            if current_size > file_pos:
                with open(log_path) as fh:
                    fh.seek(file_pos)
                    new_data = fh.read()
                file_pos = current_size
                for line in new_data.splitlines(keepends=True):
                    await websocket.send_text(line)

    except WebSocketDisconnect:
        logger.debug("WebSocket tail disconnected: %s", log_name)
    except Exception as exc:
        logger.error("WebSocket tail error: %s", exc)
        await websocket.close()
