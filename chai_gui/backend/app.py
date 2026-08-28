"""
OpenCHAI GUI — Backend Application  (v3 optimised)
FastAPI REST + WebSocket backend for HPC-AI cluster management.

Changes vs v2
─────────────
- Startup banner logs full resolved configuration
- Graceful degradation: missing optional paths do NOT crash startup
- All routers imported inside try/except so a broken module never kills the server
- /health now returns richer info (uptime, py version)
- Root redirect to /docs for discoverability
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import settings, validate_paths
from middleware.auth_middleware import AuthMiddleware

logger = logging.getLogger("openchai_gui")

# ─────────────────────────────────────────────────────────────────────────────
# Logging  (configured before any imports that might log)
# ─────────────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(LOG_DIR, "openchai_gui.log")),
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
# Router imports  (each wrapped so one broken module ≠ server crash)
# ─────────────────────────────────────────────────────────────────────────────
_ROUTERS: list[tuple] = []   # list of (router_obj, prefix, tags)

def _load(module_path: str, prefix: str, tags: list[str]) -> None:
    """Dynamically import a router module; skip and warn on failure."""
    try:
        import importlib
        mod = importlib.import_module(module_path)
        _ROUTERS.append((mod.router, prefix, tags))
        logger.debug("Loaded router: %s → %s", module_path, prefix)
    except Exception as exc:
        logger.error("⚠️  Could not load router %s (%s) — feature disabled", module_path, exc)

# ORDER MATTERS — specific routes before generic ones
_load("routes.auth",          "/auth",           ["Auth"])          # ← FIRST: public login endpoint
_load("routes.node_health",   "/nodes/health",   ["Health"])
_load("routes.cluster",        "/cluster",        ["Cluster"])
_load("routes.inventory_def",  "/inventory-def",  ["Inventory Def"])
_load("routes.deploy",         "/deploy",         ["Deploy"])
_load("routes.playbooks",      "/playbooks",      ["Playbooks"])
_load("routes.logs",           "/logs",           ["Logs"])
_load("routes.backup",         "/backup",         ["Backup"])
_load("routes.info",           "/info",           ["Info"])
_load("routes.cluster_setup",  "/cluster-setup",  ["Cluster Setup"])
_load("routes.nodes",          "/nodes",          ["Nodes"])       # generic AFTER health
_load("routes.audit",          "/audit",          ["Audit"])
_load("routes.logtail",        "/logtail",        ["Log Tail"])
_load("routes.chai_release",   "/chai-release",   ["CHAI Release"])
_load("routes.wizard_info",    "/wizard-info",    ["Wizard Info"])

# ─────────────────────────────────────────────────────────────────────────────
# Startup / shutdown
# ─────────────────────────────────────────────────────────────────────────────
_START_TIME = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("  OpenCHAI GUI Backend starting")
    logger.info("  Python   : %s", platform.python_version())
    logger.info("  Root     : %s", settings.OPENCHAI_ROOT)
    logger.info("  Ansible  : %s", settings.ANSIBLE_DIR)
    logger.info("  Routers  : %d loaded", len(_ROUTERS))
    logger.info("=" * 60)
    validate_paths()

    from services.vault_service import check_vault_readiness
    check_vault_readiness()

    from services.inventory_cli_bridge import check_bridge_readiness
    check_bridge_readiness()

    yield
    logger.info("OpenCHAI GUI backend stopped (uptime %.1fs)", time.time() - _START_TIME)

# ─────────────────────────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="OpenCHAI GUI API",
    description="REST + WebSocket backend for HPC-AI cluster management",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# JWT auth guard — runs on every request except PUBLIC_PATHS
# Must be added AFTER CORSMiddleware so CORS pre-flight (OPTIONS) passes first
app.add_middleware(AuthMiddleware)

# ─────────────────────────────────────────────────────────────────────────────
# Global exception handler — never leak Python tracebacks to the client
# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def _global_exc(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Check backend logs."},
    )

# ─────────────────────────────────────────────────────────────────────────────
# Attach routers
# ─────────────────────────────────────────────────────────────────────────────
for router_obj, prefix, tags in _ROUTERS:
    app.include_router(router_obj, prefix=prefix, tags=tags)

# ─────────────────────────────────────────────────────────────────────────────
# Built-in routes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status":           "ok",
        "version":          "3.0.0",
        "uptime_seconds":   round(time.time() - _START_TIME, 1),
        "python":           platform.python_version(),
        "openchai_root":    settings.OPENCHAI_ROOT,
        "ansible_dir":      settings.ANSIBLE_DIR,
        "playbook_library": settings.PLAYBOOK_LIBRARY,
        "routers_loaded":   len(_ROUTERS),
        "auth_enabled":     True,
    }


@app.get("/", tags=["System"])
async def root():
    return {"message": "OpenCHAI GUI API v3.0", "docs": "/docs", "health": "/health"}
