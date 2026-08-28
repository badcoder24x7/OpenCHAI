"""
OpenCHAI GUI — State Manager  (v3)

JSON-backed persistence for cluster config and node list.

Changes vs v2
─────────────
- File-level locking (fcntl) prevents corruption under concurrent saves
- Graceful recovery from partial / corrupt state files
- state_manager.nodes property added (used by node_health route)
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from typing import List

from models import ClusterState, Node

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, state_file: str) -> None:
        self._path = state_file
        os.makedirs(os.path.dirname(state_file), exist_ok=True)
        self._state: ClusterState = self._load()

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> ClusterState:
        return self._state

    @property
    def nodes(self) -> List[Node]:
        """Convenience accessor used by node_health route."""
        return self._state.nodes

    def save(self) -> None:
        """Atomically persist state to disk using file locking."""
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w") as fh:
                fcntl.flock(fh, fcntl.LOCK_EX)
                fh.write(self._state.model_dump_json(indent=2))
                fcntl.flock(fh, fcntl.LOCK_UN)
            os.replace(tmp, self._path)
            logger.debug("State persisted → %s", self._path)
        except Exception as exc:
            logger.error("State save failed: %s", exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def reset(self) -> None:
        self._state = ClusterState()
        self.save()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _load(self) -> ClusterState:
        if not os.path.exists(self._path):
            logger.info("No existing state file — starting fresh.")
            return ClusterState()
        try:
            with open(self._path) as fh:
                data = json.load(fh)
            return ClusterState(**data)
        except Exception as exc:
            logger.warning("Could not load state (%s) — resetting.", exc)
            # Back up corrupt file
            corrupt = self._path + ".corrupt"
            try:
                os.replace(self._path, corrupt)
                logger.warning("Corrupt state saved to %s", corrupt)
            except OSError:
                pass
            return ClusterState()


# Module-level singleton
from config import settings  # noqa: E402
state_manager = StateManager(settings.STATE_FILE)
