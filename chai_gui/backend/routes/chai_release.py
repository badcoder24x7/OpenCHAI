"""
OpenCHAI GUI — CHAI Release Route  (v4)

All endpoints for the 5-step CHAI Release Wizard:
  POST  /chai-release/auth
  GET   /chai-release/system-info
  GET   /chai-release/architectures
  GET   /chai-release/distributions/{arch}
  GET   /chai-release/versions/{os_dist}
  GET   /chai-release/releases/{os_dist}
  POST  /chai-release/execute
  GET   /chai-release/container-tools
  GET   /chai-release/container-versions/{tool}/{os_dist}
  GET   /chai-release/container-images/{tool}/{os_dist}/{version}
  POST  /chai-release/container-execute
  GET   /chai-release/jobs
  GET   /chai-release/jobs/{job_id}

SSL FIX: verify_ssl param defaults to None throughout — _resolve_ssl() in the
service then applies CHAI_VERIFY_SSL from the environment (default=false in
start.sh), so self-signed registries work without any frontend toggle change.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services import chai_release_service as svc
from services.chai_release_service import _resolve_ssl as _ssl_verify_flag

from fastapi.responses import PlainTextResponse
import httpx
from pathlib import Path

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class AuthPayload(BaseModel):
    auth_type: str           = "none"   # none | basic | bearer
    username:  Optional[str] = None
    password:  Optional[str] = None
    token:     Optional[str] = None


class ExecuteRequest(BaseModel):
    tarball_url:      str
    tarball_name:     str
    os_dist:          str
    os_arch:          str
    openchai_version: str
    os_label:         str           = ""
    rhel_label:       str           = ""
    el_label:         str           = ""
    kernel:           str           = ""
    verify_ssl:       Optional[bool] = None
    update_configs:   bool           = True


class ContainerDownloadItem(BaseModel):
    tool:    str
    name:    str
    url:     str
    version: str


class ContainerExecuteRequest(BaseModel):
    downloads:  List[ContainerDownloadItem]
    os_dist:    str
    verify_ssl: Optional[bool] = None


# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — Auth & system detection
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/auth", summary="Persist & VALIDATE registry credentials server-side")
async def set_auth(auth: AuthPayload, verify_ssl: Optional[bool] = Query(None)):
    """
    Stores credentials server-side AND performs a real round-trip against
    the registry to confirm they are actually accepted before returning
    success. Previously this endpoint only stored whatever was typed and
    always returned {"status": "ok"} — the frontend's "Auth applied"
    message was shown even for garbage credentials, because the real
    401 from the registry was only discovered (and silently swallowed)
    later, inside the listing endpoints.
    """
    svc.set_registry_auth(
        auth_type=auth.auth_type,
        user=auth.username  or "",
        password=auth.password or "",
        token=auth.token or "",
    )

    # "none" auth type has nothing to validate — skip the round trip.
    if auth.auth_type == "none":
        logger.info("Registry auth set to 'none' (no validation needed)")
        return {"status": "ok", "auth_type": auth.auth_type, "validated": False}

    result = await svc.validate_registry_auth(verify_ssl)

    if not result["success"]:
        logger.warning(
            "Registry auth REJECTED (type=%s, status=%s): %s",
            auth.auth_type, result["status_code"], result["error"],
        )
        # Roll back the bad credentials so a stale 401-causing password
        # isn't left in the server-side store for subsequent requests.
        svc.set_registry_auth(auth_type="none")

        # IMPORTANT: never raise HTTP 401 here. A 401 from THIS endpoint
        # means "the external HPC registry rejected these credentials" —
        # completely unrelated to the GUI's own login session. But the
        # frontend's global axios interceptor treats *any* 401 (aside from
        # /auth/login) as "the app session has expired" and logs the user
        # out entirely. That mismatch was Issue #5 — a wrong registry
        # password was logging people out of the whole application. Return
        # 200 with an in-band error instead, so this is handled purely as
        # a registry error, scoped to the CHAI Release Wizard, with the
        # user's application session left completely untouched.
        return {
            "status":    "error",
            "success":   False,
            "auth_type": auth.auth_type,
            "validated": False,
            "error":     result["error"],
        }

    logger.info("Registry auth VALIDATED via /auth endpoint (type=%s)", auth.auth_type)
    return {"status": "ok", "success": True, "auth_type": auth.auth_type, "validated": True}


@router.get("/system-info", summary="Detect local OS, arch, kernel and registry labels")
async def system_info():
    """
    Full OS detection mirroring detect_os() + collect_system_params()
    from configure_openchai_manager.py. Returns all fields needed to
    pre-fill the wizard and later update group_vars/all.yml.
    """
    return svc.detect_local_system()


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Architecture & Distribution
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/architectures", summary="List available architectures in the registry")
async def list_architectures(
    verify_ssl: Optional[bool] = Query(None, description="None = use CHAI_VERIFY_SSL env var"),
):
    items = await svc.list_architectures(verify_ssl)
    # Fallback: always show x86_64 / aarch64 so the wizard isn't empty
    return {"architectures": items or ["x86_64", "aarch64"]}


@router.get("/distributions/{arch}", summary="List OS distributions for an architecture")
async def list_distributions(
    arch: str,
    verify_ssl: Optional[bool] = Query(None),
):
    items = await svc.list_distributions(arch, verify_ssl)
    if not items:
        logger.warning(
            "Empty distributions for arch=%s verify_ssl=%s — "
            "check registry URL, credentials, and CHAI_VERIFY_SSL setting.",
            arch, verify_ssl,
        )
    return {"arch": arch, "distributions": items}


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — OpenCHAI Version (tarballs)
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/versions/{arch}/{os_dist}",
    summary="List available OpenCHAI tarballs / installed versions"
)
async def list_versions(
    arch: str,
    os_dist: str,
    verify_ssl: Optional[bool] = Query(None),
):
    """
    Example:
      /chai-release/versions/x86_64/rocky9.6
    """

    logger.info(
        "Listing versions for arch=%s os_dist=%s verify_ssl=%s",
        arch,
        os_dist,
        verify_ssl,
    )

    items = await svc.list_versions(
        arch=arch,
        os_dist=os_dist,
        verify_ssl=verify_ssl,
    )

    return {
        "arch": arch,
        "os_dist": os_dist,
        "versions": items,
    }

# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Release mapping
# ─────────────────────────────────────────────────────────────────────────────
@router.get(
    "/local-architectures",
    summary="List architectures present in the local registry mirror only "
            "(no registry call — used by the skip-authentication path)"
)
async def local_architectures():
    return {"architectures": await svc.list_local_archs()}


@router.get(
    "/local-distributions/{arch}",
    summary="List distributions present locally for an arch (skip-auth path)"
)
async def local_distributions(arch: str):
    return {"distributions": await svc.list_local_dists(arch)}


@router.get(
    "/release-notes",
    summary="List local release notes WITHOUT requiring a version (used by the "
            "Release step that now appears before the Version step)"
)
async def release_notes():
    return await svc.list_release_notes()


@router.get(
    "/releases/{arch}/{os_dist}/{openchai_version}",
    summary="List releases linked to an OpenCHAI version"
)
async def list_releases(
    arch: str,
    os_dist: str,
    openchai_version: str,
    verify_ssl: Optional[bool] = Query(None),
):
    """
    Example:
      /chai-release/releases/x86_64/rocky9.6?openchai_version=v1.0
    """

    logger.info(
        "Listing releases for arch=%s os_dist=%s version=%s",
        arch,
        os_dist,
        openchai_version,
    )

    result = await svc.list_releases(
        arch=arch,
        os_dist=os_dist,
        openchai_version=openchai_version,
        verify_ssl=verify_ssl,
    )

    return result

@router.get(
    "/release-content",
    summary="Get release asset content"
)
async def release_content(
    path: str,
    asset_type: str = "release_notes",
    verify_ssl: Optional[bool] = Query(None),
):
    """
    Return markdown/text content for local or remote assets.
    """

    try:
        #
        # Local markdown file
        #
        if asset_type == "release_notes":
            p = Path(path)

            if not p.exists():
                raise HTTPException(status_code=404, detail="File not found")

            return PlainTextResponse(
                p.read_text(encoding="utf-8")
            )

        #
        # Remote registry asset — use the same authenticated client as every
        # other registry call so assets behind auth are actually fetchable.
        #
        async with svc._build_client(verify_ssl, timeout=20) as client:

            resp = await client.get(path)

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Failed to fetch remote asset: {resp.status_code}"
                )

            return PlainTextResponse(resp.text)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
# ─────────────────────────────────────────────────────────────────────────────
# Cluster Configuration tab — local install check
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/local-install-status",
    summary="Check whether an OpenCHAI package is installed locally, for the "
            "Cluster Configuration tab's install-gate check",
)
async def local_install_status():
    return svc.get_local_install_status()


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Execute
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/execute", summary="Download, extract and configure an OpenCHAI release")
async def execute_release(req: ExecuteRequest):
    if not req.openchai_version:
        raise HTTPException(status_code=400, detail="openchai_version is required")

    job_id = await svc.execute_release(
        tarball_url=req.tarball_url,
        tarball_name=req.tarball_name,
        os_dist=req.os_dist,
        os_arch=req.os_arch,
        openchai_version=req.openchai_version,
        os_label=req.os_label,
        rhel_label=req.rhel_label,
        el_label=req.el_label,
        kernel=req.kernel,
        verify_ssl=req.verify_ssl,
        update_configs=req.update_configs,
    )
    return {"job_id": job_id, "status": "running"}


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 — Container images (mirrors container_img_selector.py)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/container-tools", summary="List known container image tools")
async def container_tools():
    return {"tools": await svc.list_container_tools()}


@router.get("/container-versions/{tool}/{os_dist}",
            summary="List available versions for a container tool")
async def container_versions(
    tool: str,
    os_dist: str,
    verify_ssl: Optional[bool] = Query(None),
):
    items = await svc.list_container_versions(tool, os_dist, verify_ssl)
    return {"tool": tool, "os_dist": os_dist, "versions": items}


@router.get("/container-images/{tool}/{os_dist}/{version}",
            summary="List downloadable container images for a tool/version")
async def container_images(
    tool: str,
    os_dist: str,
    version: str,
    verify_ssl: Optional[bool] = Query(None),
):
    items = await svc.list_container_images(tool, os_dist, version, verify_ssl)
    return {"tool": tool, "os_dist": os_dist, "version": version, "images": items}


@router.post("/container-execute", summary="Download selected container images")
async def container_execute(req: ContainerExecuteRequest):
    if not req.downloads:
        raise HTTPException(status_code=400, detail="No downloads specified")
    job_id = await svc.execute_container_download(
        downloads=[d.dict() for d in req.downloads],
        os_dist=req.os_dist,
        verify_ssl=req.verify_ssl,
    )
    return {"job_id": job_id, "status": "running"}


# ─────────────────────────────────────────────────────────────────────────────
# Job polling
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/jobs", summary="List all CHAI release jobs")
async def list_jobs():
    return {"jobs": svc.list_jobs()}


@router.get("/jobs/{job_id}", summary="Get status and log for a specific job")
async def get_job(job_id: str):
    job = svc.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job
