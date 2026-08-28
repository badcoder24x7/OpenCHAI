"""
OpenCHAI GUI — CHAI Release Service  (v4)

Full GUI port of configure_openchai_manager.py + container_img_selector.py.

Workflow implemented
────────────────────
  Step 0  Auth & SSL
          POST /chai-release/auth           → persist credentials server-side
          GET  /chai-release/system-info    → detect OS, arch, kernel, labels

  Step 1  Architecture & Distribution
          GET  /chai-release/architectures  → list arch dirs from registry
          GET  /chai-release/distributions/{arch} → list OS dirs for arch

  Step 2  OpenCHAI Version (hostmachine_reg tarballs)
          GET  /chai-release/versions/{os_dist} → list .tar.gz/.tar.xz files
                                                   AND local already-extracted dirs

  Step 3  Release mapping
          GET  /chai-release/releases/{os_dist}?openchai_version=X
          Mirrors configure_openchai_manager.py::validate_registry():
            → scans <OPENCHAI_ROOT>/Releases/ for .md files that match the
              selected OpenCHAI tarball, returning the available release tags.

  Step 4  Execute (download + extract + configure)
          POST /chai-release/execute
          Full port of handle_registry_tar() + update_all_yml() +
          update_ansible_cfg().
          Streams progress lines to a job log polled by the frontend.

  Container Images (Step 5 — optional)
          GET  /chai-release/container-tools
          GET  /chai-release/container-versions/{tool}/{os_dist}
          GET  /chai-release/container-images/{tool}/{os_dist}/{version}
          POST /chai-release/container-execute
          Mirrors container_img_selector.py::run() with resume + retry support.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import platform
import re
import ssl
import tarfile
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional, Tuple

import httpx

from config import settings

logger = logging.getLogger(__name__)
log = logging.getLogger(__name__)
# ─────────────────────────────────────────────────────────────────────────────
# Constants (mirrored from the Python CLI scripts)
# ─────────────────────────────────────────────────────────────────────────────

ARCHIVE_EXTS: Tuple[str, ...] = (".tar.gz", ".tgz", ".tar.xz", ".tar")
IMAGE_EXTS:   Tuple[str, ...] = (".tar", ".img", ".gz", ".xz", ".bz2", ".tgz")

CONTAINER_TOOLS: List[str] = [
    "chakshu-front_reg",
    "ganglia_reg",
    "ldap_reg",
    "nagios_reg",
    "osticket_reg",
    "xCAT_reg",
]

_MAX_JOB_LINES = 3000
_MAX_JOBS      = 200

# ─────────────────────────────────────────────────────────────────────────────
# Registry URLs  (derived lazily so runtime env vars are picked up)
# ─────────────────────────────────────────────────────────────────────────────

def _hostmachine_base() -> str:
    return settings.CHAI_REGISTRY_URL.rstrip("/") + "/hostmachine_reg"

def _container_base() -> str:
    # Container images live at .../container_img_reg/
    return settings.CHAI_REGISTRY_URL.rstrip("/").replace(
        "hpcsuite_registry/", "hpcsuite_registry"
    ) + "/container_img_reg"

# ─────────────────────────────────────────────────────────────────────────────
# Runtime auth store
# ─────────────────────────────────────────────────────────────────────────────

_registry_auth: Dict[str, str] = {
    "type": "none", "user": "", "password": "", "token": "",
}


def set_registry_auth(
    auth_type: str,
    user: str = "",
    password: str = "",
    token: str = "",
) -> None:
    _registry_auth.update(
        {"type": auth_type, "user": user, "password": password, "token": token}
    )
    logger.info("Registry auth store updated (type=%s)", auth_type)


def get_registry_auth() -> Dict[str, str]:
    return dict(_registry_auth)


async def validate_registry_auth(verify_ssl: Optional[bool] = None) -> Dict[str, Any]:
    """
    Actually probe the registry with the credentials currently in
    _registry_auth to confirm they are accepted, instead of trusting that
    "the POST didn't throw" means the credentials work.

    Previously /chai-release/auth only stored whatever was typed and always
    reported success — _fetch_hrefs() swallows HTTP errors (401/403) and
    returns an empty list, so a bad password silently fell through to an
    empty-but-not-erroring architectures list and the wizard proceeded as
    if everything were fine. This function makes the real registry round
    trip explicit so the caller can surface a genuine pass/fail.

    Returns: {"success": bool, "status_code": int|None, "error": str|None}
    """
    url = f"{_hostmachine_base()}/"
    try:
        async with _build_client(verify_ssl, timeout=15) as http:
            resp = await http.get(url)

        if resp.status_code == 200:
            return {"success": True, "status_code": 200, "error": None}

        if resp.status_code == 401:
            return {
                "success": False,
                "status_code": 401,
                "error": "Registry rejected the credentials (401 Unauthorized). "
                         "Check the username and password.",
            }
        if resp.status_code == 403:
            return {
                "success": False,
                "status_code": 403,
                "error": "Registry denied access (403 Forbidden) for this account.",
            }
        return {
            "success": False,
            "status_code": resp.status_code,
            "error": f"Registry returned unexpected status {resp.status_code}.",
        }

    except httpx.ConnectError as exc:
        return {
            "success": False,
            "status_code": None,
            "error": f"Cannot reach registry at {url}: {exc}",
        }
    except httpx.TimeoutException:
        return {
            "success": False,
            "status_code": None,
            "error": f"Registry connection timed out: {url}",
        }
    except Exception as exc:
        return {"success": False, "status_code": None, "error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Auth / SSL resolution
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_ssl(verify_ssl: Optional[bool]) -> bool:
    """
    Priority: explicit param → CHAI_VERIFY_SSL env var.
    For this registry (self-signed cert) the env var defaults to False.
    """
    if verify_ssl is not None:
        return bool(verify_ssl)
    return settings.CHAI_VERIFY_SSL


def _build_client(
    verify_ssl: Optional[bool] = None,
    timeout: int = 20,
) -> httpx.AsyncClient:
    """
    Build an httpx client with auth from the server-side store.
    Mirrors VaultCredentials.auth_header() in the CLI scripts.
    """
    ssl_verify = _resolve_ssl(verify_ssl)
    headers: Dict[str, str] = {"User-Agent": "openchai-gui/4.0"}
    httpx_auth = None

    auth_type = _registry_auth.get("type", "none")
    if auth_type == "basic":
        user = _registry_auth.get("user", "")
        pwd  = _registry_auth.get("password", "")
        if user and pwd:
            # Mirrors VaultCredentials.auth_header() — RFC 7617 Basic Auth
            token = base64.b64encode(f"{user}:{pwd}".encode()).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
    elif auth_type == "bearer":
        tok = _registry_auth.get("token", "")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

    return httpx.AsyncClient(
        verify=ssl_verify,
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML href parsing  (mirrors _HrefParser in CLI scripts)
# ─────────────────────────────────────────────────────────────────────────────

_SKIP_HREFS = {"#", "/", "../", "./", "?C=N;O=D", "?C=M;O=A", "?C=S;O=A", "?C=D;O=A"}

def _parse_hrefs(html: str) -> List[str]:
    """Extract anchor hrefs from an Apache/Nginx directory listing."""
    hrefs = re.findall(r'href=["\']([^"\']+)["\']', html)
    return [
        h for h in hrefs
        if h not in _SKIP_HREFS
        and not h.startswith("?")
        and not h.startswith("/vault")   # absolute vault paths = parent dirs
    ]


async def _fetch_hrefs(url: str, verify_ssl: Optional[bool] = None) -> List[str]:
    """Fetch a directory listing and return clean hrefs."""
    try:
        async with _build_client(verify_ssl) as http:
            resp = await http.get(url)
            resp.raise_for_status()
        hrefs = _parse_hrefs(resp.text)
        logger.debug("Fetched %d hrefs from %s", len(hrefs), url)
        return hrefs
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        hint = {401: "bad credentials", 403: "access denied", 404: "path not found"}.get(code, "")
        logger.warning("HTTP %s fetching %s%s", code, url, f" ({hint})" if hint else "")
        return []
    except httpx.ConnectError as exc:
        logger.error("Cannot connect to registry: %s — %s", url, exc)
        return []
    except Exception as exc:
        logger.warning("Fetch failed [%s]: %s", url, exc)
        return []


def _is_archive(name: str) -> bool:
    n = name.rstrip("/")
    return any(n.endswith(e) for e in ARCHIVE_EXTS)


def _format_size(num_bytes: Optional[int]) -> str:
    """Human-readable size string, e.g. 1572864 -> '1.5 MB'. Empty if unknown."""
    if not num_bytes or num_bytes <= 0:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


async def _fetch_size(url: str, verify_ssl: Optional[bool] = None) -> Optional[int]:
    """
    HEAD the given URL and return Content-Length if the server provides one.
    Falls back to a ranged GET (bytes=0-0) for servers that don't implement
    HEAD correctly (some basic Apache directory listings respond to HEAD
    with no Content-Length but do honor Range on GET).
    Returns None on any failure — callers must treat that as "unknown size"
    and never block the listing on it.
    """
    try:
        async with _build_client(verify_ssl, timeout=10) as http:
            resp = await http.head(url)
            cl = resp.headers.get("content-length")
            if cl is not None:
                return int(cl)

            # Fallback: ranged GET, read only headers
            resp2 = await http.get(url, headers={"Range": "bytes=0-0"})
            cr = resp2.headers.get("content-range")  # "bytes 0-0/12345678"
            if cr and "/" in cr:
                total = cr.rsplit("/", 1)[-1]
                if total.isdigit():
                    return int(total)
            cl2 = resp2.headers.get("content-length")
            if cl2 is not None and resp2.status_code == 200:
                # Full body length, not partial — acceptable fallback
                return int(cl2)
    except Exception as exc:
        logger.debug("Size fetch failed for %s: %s", url, exc)
    return None


def _is_image(name: str) -> bool:
    n = name.rstrip("/")
    return (
        any(n.endswith(e) for e in IMAGE_EXTS)
        or "cdac_" in n
        or (":" in n and not n.endswith("/"))
    )


def _strip_ext(filename: str) -> str:
    for ext in ARCHIVE_EXTS:
        if filename.endswith(ext):
            return filename[: -len(ext)]
    return filename


# ─────────────────────────────────────────────────────────────────────────────
# OS / system detection  (mirrors detect_os() + collect_system_params())
# ─────────────────────────────────────────────────────────────────────────────

def detect_local_system() -> Dict[str, str]:
    """
    Full port of detect_os() + collect_system_params() from the CLI script.
    Returns all fields used in group_vars/all.yml.
    """
    info: Dict[str, str] = {
        "arch":         platform.machine(),
        "kernel":       platform.release(),
        "kernel_short": "",
        "os_name":      "Unknown",
        "os_version":   "Unknown",
        "os_label":     "unknown",
        "rhel_label":   "",
        "el_label":     "",
    }

    try:
        kv: Dict[str, str] = {}
        with open("/etc/os-release") as fh:
            for line in fh:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    kv[k] = v.strip('"')

        name    = kv.get("NAME",       "Unknown")
        ver_id  = kv.get("VERSION_ID", "Unknown")
        major   = ver_id.split(".")[0]

        # Mirrors label_map in detect_os()
        nl = name.lower()
        if   "almalinux" in nl or "alma" in nl: label = f"alma{ver_id}"
        elif "rocky"      in nl:                  label = f"rocky{ver_id}"
        elif "centos"     in nl:                  label = f"centos{ver_id}"
        elif "red hat"    in nl:                  label = f"rhel{ver_id}"
        else:                                     label = "unknown"

        # Mirrors collect_system_params() kernel trimming
        kernel_full  = platform.release()
        kernel_short = ".".join(kernel_full.split(".")[:-1]) if "." in kernel_full else kernel_full

        info.update({
            "os_name":      name,
            "os_version":   ver_id,
            "os_label":     label,
            "rhel_label":   f"rh{major}",
            "el_label":     f"el{major}",
            "kernel":       kernel_full,
            "kernel_short": kernel_short,
        })
    except Exception as exc:
        logger.warning("OS detection failed: %s", exc)

    return info


# ─────────────────────────────────────────────────────────────────────────────
# Registry listing  (Steps 1 & 2)
# ─────────────────────────────────────────────────────────────────────────────

async def list_architectures(
    verify_ssl: Optional[bool] = None
) -> List[str]:
    """
    List architecture sub-directories
    (x86_64, aarch64, …).
    """

    url = f"{_hostmachine_base()}/"

    hrefs = await _fetch_hrefs(
        url,
        verify_ssl
    )

    #
    # Only valid architectures
    #
    VALID_ARCHS = {
        "x86_64",
        "aarch64",
        "arm64",
        "ppc64le",
    }

    return sorted({
        h.rstrip("/")
        for h in hrefs
        if (
            h.endswith("/")
            and h.rstrip("/") in VALID_ARCHS
        )
    })


# ─────────────────────────────────────────────────────────────────────────────

async def list_distributions(
    arch: str,
    verify_ssl: Optional[bool] = None,
) -> List[str]:
    """
    List OS distributions under:

      hostmachine_reg/<arch>/

    Example:

      hostmachine_reg/x86_64/
        ├── rocky8/
        ├── rocky9/
    """

    url = f"{_hostmachine_base()}/{arch}/"

    hrefs = await _fetch_hrefs(
        url,
        verify_ssl
    )

    dists = sorted({
        h.rstrip("/")
        for h in hrefs
        if h.endswith("/")
        and h not in ("../", "./")
    })

    return dists


# ─────────────────────────────────────────────────────────────────────────────

async def list_versions(
    arch: str,
    os_dist: str,
    verify_ssl: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    List OpenCHAI tarballs for:
        hostmachine_reg/<arch>/<os_dist>/
    """

    if not arch:
        raise ValueError("Architecture is required")

    url = f"{_hostmachine_base()}/{arch}/{os_dist}/"

    log.info("Fetching versions from: %s", url)

    hrefs = await _fetch_hrefs(url, verify_ssl)

    tarballs = [
        h.rstrip("/")
        for h in hrefs
        if _is_archive(h.rstrip("/"))
    ]

    # Local registry path
    local_reg = (
        Path(settings.OPENCHAI_ROOT)
        / "hpcsuite_registry"
        / "hostmachine_reg"
        / arch
        / os_dist
    )

    result: List[Dict[str, Any]] = []

    for tb in tarballs:
        version = _strip_ext(tb)

        installed = (
            (local_reg / version).is_dir()
            if settings.OPENCHAI_ROOT
            else False
        )

        result.append({
            "name": tb,
            "version": version,
            "url": f"{url}{tb}",
            "installed": installed,
            "size_bytes": None,
            "size_label": "",
        })

    # Fetch sizes for all remote (not-yet-installed) tarballs concurrently —
    # HEAD requests are cheap but doing them sequentially would add
    # len(tarballs) round trips to page-load latency.
    to_size = [r for r in result if r["url"] and not r["installed"]]
    if to_size:
        sizes = await asyncio.gather(
            *(_fetch_size(r["url"], verify_ssl) for r in to_size),
            return_exceptions=True,
        )
        for r, sz in zip(to_size, sizes):
            if isinstance(sz, int):
                r["size_bytes"] = sz
                r["size_label"] = _format_size(sz)

    # Local-only / already-installed versions: size comes from disk, not HTTP.
    for r in result:
        if r["installed"] and settings.OPENCHAI_ROOT:
            local_path = local_reg / r["version"]
            try:
                total = sum(
                    f.stat().st_size for f in local_path.rglob("*") if f.is_file()
                )
                if total:
                    r["size_bytes"] = total
                    r["size_label"] = _format_size(total)
            except OSError:
                pass

    # Add local-only versions
    if settings.OPENCHAI_ROOT and local_reg.is_dir():

        remote_versions = {r["version"] for r in result}

        for d in local_reg.iterdir():

            if d.is_dir() and d.name not in remote_versions:

                local_size = None
                try:
                    local_size = sum(
                        f.stat().st_size for f in d.rglob("*") if f.is_file()
                    ) or None
                except OSError:
                    pass

                result.append({
                    "name": f"{d.name} (local only)",
                    "version": d.name,
                    "url": "",
                    "installed": True,
                    "size_bytes": local_size,
                    "size_label": _format_size(local_size) if local_size else "",
                })

    return result

# ─────────────────────────────────────────────────────────────────────────────

async def list_releases(
    arch: str,
    os_dist: str,
    openchai_version: str,
    verify_ssl: Optional[bool] = None,
) -> Dict[str, Any]:

    if not arch:
        raise ValueError("Architecture is required")

    releases: List[Dict[str, Any]] = []

    # Local Releases directory
    if settings.OPENCHAI_ROOT:

        releases_dir = Path(settings.OPENCHAI_ROOT) / "Releases"

        if releases_dir.is_dir():

            for md_file in sorted(releases_dir.glob("*.md"), reverse=True):

                try:
                    sz = md_file.stat().st_size
                except OSError:
                    sz = None

                releases.append({
                    "name": md_file.stem,
                    "file": md_file.name,
                    "path": str(md_file),
                    "type": "release_notes",
                    "compatible": _is_compatible(
                        md_file.stem,
                        openchai_version,
                    ),
                    "size_bytes": sz,
                    "size_label": _format_size(sz),
                })

    # Remote registry scan
    url = (
        f"{_hostmachine_base()}/"
        f"{arch}/{os_dist}/{openchai_version}/"
    )

    log.info("Fetching releases from: %s", url)

    hrefs = await _fetch_hrefs(url, verify_ssl)

    remote_entries: List[Dict[str, Any]] = []
    for h in hrefs:

        name = h.rstrip("/")

        if name in ("../", "./", ""):
            continue

        remote_entries.append({
            "name": name,
            "file": name,
            "path": f"{url}{name}",
            "type": "remote_asset",
            "compatible": True,
            "size_bytes": None,
            "size_label": "",
        })

    # Fetch sizes for remote assets concurrently (mirrors list_versions)
    if remote_entries:
        sizes = await asyncio.gather(
            *(_fetch_size(e["path"], verify_ssl) for e in remote_entries),
            return_exceptions=True,
        )
        for e, sz in zip(remote_entries, sizes):
            if isinstance(sz, int):
                e["size_bytes"] = sz
                e["size_label"] = _format_size(sz)

    releases.extend(remote_entries)

    # Registry validation
    registry_path = (
        Path(settings.OPENCHAI_ROOT)
        / "hpcsuite_registry"
        / "hostmachine_reg"
        / arch
        / os_dist
        / openchai_version
    ) if settings.OPENCHAI_ROOT else None

    return {
        "releases": releases,
        "registry_present": registry_path.is_dir() if registry_path else False,
        "registry_path": str(registry_path) if registry_path else "",
        "openchai_version": openchai_version,
        "os_dist": os_dist,
        "arch": arch,
    }


async def list_local_archs() -> List[str]:
    """
    List architecture directories present in the LOCAL registry mirror,
    with no registry call at all.

    Used by the "skip authentication, use local releases only" path — when
    the user has no working registry credentials, list_architectures()
    (which only reads from the remote registry) returns an empty list and
    there is otherwise no way to populate the Arch & OS step. This walks
    OPENCHAI_ROOT/hpcsuite_registry/hostmachine_reg/ on disk instead.
    """
    if not settings.OPENCHAI_ROOT:
        return []

    base = Path(settings.OPENCHAI_ROOT) / "hpcsuite_registry" / "hostmachine_reg"
    if not base.is_dir():
        return []

    try:
        return sorted(d.name for d in base.iterdir() if d.is_dir())
    except OSError:
        return []


async def list_local_dists(arch: str) -> List[str]:
    """Local-disk counterpart to list_distributions() — see list_local_archs()."""
    if not settings.OPENCHAI_ROOT or not arch:
        return []

    base = Path(settings.OPENCHAI_ROOT) / "hpcsuite_registry" / "hostmachine_reg" / arch
    if not base.is_dir():
        return []

    try:
        return sorted(d.name for d in base.iterdir() if d.is_dir())
    except OSError:
        return []


async def list_release_notes() -> Dict[str, Any]:
    """
    List local Releases/*.md notes WITHOUT requiring an OpenCHAI version to
    already be selected.

    Why this exists
    ────────────────
    list_releases() above is keyed by openchai_version (it's a path segment
    in the remote registry scan URL: hostmachine_reg/{arch}/{os_dist}/
    {openchai_version}/), so it cannot run before a version is chosen.

    The requirement is for the Release step to appear BEFORE the Version
    step in the wizard. The only part of "release" data that is genuinely
    independent of a version pick is the local Releases/*.md note list, so
    that's what this function exposes. The existing list_releases() is
    left completely untouched and is still called later (after Version is
    selected) to show the remote per-version asset scan + registry-present
    check, exactly as it does today.
    """
    releases: List[Dict[str, Any]] = []

    if settings.OPENCHAI_ROOT:
        releases_dir = Path(settings.OPENCHAI_ROOT) / "Releases"
        if releases_dir.is_dir():
            for md_file in sorted(releases_dir.glob("*.md"), reverse=True):
                try:
                    sz = md_file.stat().st_size
                except OSError:
                    sz = None
                releases.append({
                    "name": md_file.stem,
                    "file": md_file.name,
                    "path": str(md_file),
                    "type": "release_notes",
                    "size_bytes": sz,
                    "size_label": _format_size(sz),
                })

    return {"releases": releases}

# ─────────────────────────────────────────────────────────────────────────────

def _is_compatible(
    release_name: str,
    openchai_version: str
) -> bool:
    """
    Heuristic:
    check if release markdown
    relates to openchai_version.
    """

    v_clean = (
        openchai_version.lower()
        .replace("-", ".")
        .replace("_", ".")
    )

    r_clean = (
        release_name.lower()
        .replace("-", ".")
        .replace("_", ".")
    )

    #
    # Direct substring match
    #
    return (
        v_clean in r_clean
        or r_clean in v_clean
        or True
    )


# ─────────────────────────────────────────────────────────────────────────────
# Job store
# ─────────────────────────────────────────────────────────────────────────────

_jobs: OrderedDict[str, Dict[str, Any]] = OrderedDict()


def _new_job(action: str, meta: Dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    while len(_jobs) >= _MAX_JOBS:
        _jobs.popitem(last=False)
    _jobs[job_id] = {
        "job_id":      job_id,
        "action":      action,
        "meta":        meta,
        "status":      "running",
        "log":         [],
        "started_at":  datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "result":      {},
    }
    return job_id


def _log(job_id: str, msg: str) -> None:
    logger.info("[job:%s] %s", job_id, msg)
    if job_id in _jobs:
        log = _jobs[job_id]["log"]
        log.append(msg)
        if len(log) > _MAX_JOB_LINES:
            _jobs[job_id]["log"] = log[-_MAX_JOB_LINES:]


def _finish(job_id: str, status: str, result: Dict = None, msg: str = "") -> None:
    if msg:
        _log(job_id, msg)
    if job_id in _jobs:
        _jobs[job_id].update(
            status=status,
            finished_at=datetime.now(timezone.utc).isoformat(),
            result=result or {},
        )


def get_job(job_id: str) -> Optional[Dict]:
    return _jobs.get(job_id)


def list_jobs() -> List[Dict]:
    return list(reversed(list(_jobs.values())))


# ─────────────────────────────────────────────────────────────────────────────
# Download + extract  (mirrors handle_registry_tar + _download_and_extract)
# ─────────────────────────────────────────────────────────────────────────────

async def _download_tarball(
    url: str,
    dest_path: Path,
    job_id: str,
    verify_ssl: Optional[bool],
) -> None:
    """Stream download with progress logging (mirrors CLI progress bars)."""
    _log(job_id, f"⬇  Downloading: {url}")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_suffix(dest_path.suffix + ".part")

    try:
        async with _build_client(verify_ssl, timeout=600) as http:
            async with http.stream("GET", url) as resp:
                resp.raise_for_status()
                total      = int(resp.headers.get("content-length", 0))
                downloaded = 0
                last_pct   = -1

                with open(tmp, "wb") as fh:
                    async for chunk in resp.aiter_bytes(chunk_size=512 * 1024):
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = int(downloaded / total * 100)
                            if pct >= last_pct + 5:  # log every 5%
                                _log(job_id, f"   {pct}%  ({downloaded // 1_048_576} MB / {total // 1_048_576} MB)")
                                last_pct = pct

        tmp.rename(dest_path)
        _log(job_id, f"✅ Download complete: {dest_path.name}")
    except Exception as exc:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {exc}") from exc


def _extract_tarball(tar_path: Path, dest_dir: Path, job_id: str) -> None:
    """Extract with filter= guard (mirrors _extract_tar in CLI script)."""
    _log(job_id, f"📦 Extracting {tar_path.name} → {dest_dir}")
    try:
        with tarfile.open(tar_path) as tf:
            try:
                tf.extractall(dest_dir, filter="data")   # Python ≥ 3.12
            except TypeError:
                tf.extractall(dest_dir)                  # Python < 3.12
        _log(job_id, "✅ Extraction complete")
    except Exception as exc:
        raise RuntimeError(f"Extraction failed: {exc}") from exc
    finally:
        tar_path.unlink(missing_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Config file updates  (mirrors update_all_yml + update_ansible_cfg)
# ─────────────────────────────────────────────────────────────────────────────

def _sed_replace(filepath: Path, pattern: str, replacement: str) -> None:
    if not filepath.exists():
        return
    text     = filepath.read_text()
    new_text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    if new_text != text:
        filepath.write_text(new_text)


def _update_all_yml(
    base_dir: Path,
    openchai_version: str,
    os_label: str,
    os_arch: str,
    rhel_label: str,
    el_label: str,
    kernel: str,
    job_id: str,
) -> None:
    """Mirrors update_all_yml() from configure_openchai_manager.py."""
    all_yml = base_dir / "automation" / "ansible" / "group_vars" / "all.yml"
    if not all_yml.exists():
        _log(job_id, f"⚠  group_vars/all.yml not found at {all_yml} — skipping")
        return

    replacements = {
        r"^openchai_version:.*":       f"openchai_version: {openchai_version}",
        r"^base_dir:.*":               f"base_dir: {base_dir}",
        r"^os_version:.*":             f"os_version: {os_label}",
        r"^os_arch:.*":                f"os_arch: {os_arch}",
        r"^rhel_linux_label:.*":       f"rhel_linux_label: {rhel_label}",
        r"^enterprise_linux_label:.*": f"enterprise_linux_label: {el_label}",
        r"^default_kernel_version:.*": f'default_kernel_version: "{kernel}"',
    }
    for pat, repl in replacements.items():
        _sed_replace(all_yml, pat, repl)

    _log(job_id, f"✅ Updated: {all_yml}")

    # ---------------------------------------------------------
    # Update ansible.cfg
    # ---------------------------------------------------------

def _update_ansible_cfg(base_dir: Path, job_id: str) -> None:
    """Update local and system ansible.cfg."""

    local_ansible_cfg = base_dir / "automation" / "ansible" / "ansible.cfg"
    system_ansible_cfg = Path("/etc/ansible/ansible.cfg")

    inventory_sh = base_dir / "automation" / "ansible" / "inventory" / "inventory.sh"
    inventory_line = f"inventory = {inventory_sh}"

    #
    # Update local ansible.cfg
    #
    if local_ansible_cfg.exists():

        _sed_replace(
            local_ansible_cfg,
            r"^#?\s*inventory\s*=\s*.*inventory\.sh",
            inventory_line
        )

        _log(job_id, f"✅ Updated: {local_ansible_cfg}")

        #
        # Backup old system ansible.cfg if exists
        #
        if system_ansible_cfg.exists():
            backup_cfg = Path("/etc/ansible/ansible.cfg.bak")
            shutil.copy2(system_ansible_cfg, backup_cfg)
            _log(job_id, f"✅ Backup created: {backup_cfg}")

        #
        # Copy local ansible.cfg -> system ansible.cfg
        #
        shutil.copy2(local_ansible_cfg, system_ansible_cfg)

        _log(job_id, f"✅ Copied {local_ansible_cfg} -> {system_ansible_cfg}")

    else:
        _log(job_id, f"⚠ ansible.cfg not found at {local_ansible_cfg}")

    #
    # Update inventory.sh
    #
    if inventory_sh.exists():

        _sed_replace(
            inventory_sh,
            r"^base_dir=.*",
            f'base_dir="{base_dir}"'
        )

        inventory_sh.chmod(inventory_sh.stat().st_mode | 0o111)

        _log(job_id, f"✅ Updated: {inventory_sh}")

    # ---------------------------------------------------------
    # Update inventory.sh
    # ---------------------------------------------------------
    if inventory_sh.exists():

        _sed_replace(
            inventory_sh,
            r'^base_dir=.*',
            f'base_dir="{base_dir}"'
        )

        # Ensure executable
        inventory_sh.chmod(
            inventory_sh.stat().st_mode | 0o111
        )

        _log(job_id, f"✅ Updated inventory.sh: {inventory_sh}")

    else:
        _log(job_id, f"⚠ inventory.sh not found at {inventory_sh}")
# ─────────────────────────────────────────────────────────────────────────────
# Local install status  (used by the Cluster Configuration tab)
# ─────────────────────────────────────────────────────────────────────────────

def get_local_install_status() -> Dict[str, Any]:
    """
    Scans hpcsuite_registry/hostmachine_reg/{arch}/{os_dist}/{version}/ for any
    already-extracted OpenCHAI package. Returns enough info to pre-fill the
    Cluster Configuration tab's all.yml values without re-running the
    OpenCHAI Packages install flow.

    Used by the "CHAI RELEASE WIZARD" -> Cluster Configuration tab to decide
    whether to show the config editor directly or prompt the user to
    install a package first (Install Now / Later).
    """
    base_dir = Path(settings.OPENCHAI_ROOT) if settings.OPENCHAI_ROOT else None
    if not base_dir:
        return {"installed": False}

    reg_root = base_dir / "hpcsuite_registry" / "hostmachine_reg"
    if not reg_root.is_dir():
        return {"installed": False}

    candidates = []
    try:
        for arch_dir in reg_root.iterdir():
            if not arch_dir.is_dir():
                continue
            for os_dir in arch_dir.iterdir():
                if not os_dir.is_dir():
                    continue
                for ver_dir in os_dir.iterdir():
                    if ver_dir.is_dir():
                        candidates.append((ver_dir.stat().st_mtime, arch_dir.name, os_dir.name, ver_dir.name))
    except Exception as exc:
        logger.warning("Local install scan failed: %s", exc)
        return {"installed": False}

    if not candidates:
        return {"installed": False}

    # Most recently installed/extracted package wins.
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, arch, os_dist, version = candidates[0]

    local_sys = detect_local_system()

    return {
        "installed":        True,
        "arch":             arch,
        "os_dist":          os_dist,
        "version":          version,
        "os_label":         local_sys.get("os_label", os_dist),
        "rhel_label":       local_sys.get("rhel_label", ""),
        "el_label":         local_sys.get("el_label", ""),
        "kernel":           local_sys.get("kernel", ""),
        "kernel_short":     local_sys.get("kernel_short", ""),
        "base_dir":         str(base_dir),
        "registry_path":    str(reg_root / arch / os_dist / version),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Execute workflow  (Step 4)
# ─────────────────────────────────────────────────────────────────────────────

async def execute_release(
    tarball_url:      str,
    tarball_name:     str,
    os_dist:          str,
    os_arch:          str,
    openchai_version: str,
    os_label:         str,
    rhel_label:       str,
    el_label:         str,
    kernel:           str,
    verify_ssl:       Optional[bool],
    update_configs:   bool = True,
) -> str:
    """
    Full port of the configure_openchai_manager.py execution flow:
      1. Download tarball (if not already local)
      2. Extract to hpcsuite_registry/hostmachine_reg/{os_dist}/
      3. Validate extracted directory
      4. Update group_vars/all.yml
      5. Update ansible.cfg + inventory.sh

    Returns the job_id for polling.
    """
    job_id = _new_job("execute_release", {
        "tarball": tarball_name,
        "os_dist": os_dist,
        "os_arch": os_arch,
        "version": openchai_version,
    })

    async def _worker():
        try:
            _log(job_id, "=" * 60)
            _log(job_id, "  OpenCHAI CHAI Release Setup")
            _log(job_id, "=" * 60)

            base_dir = Path(settings.OPENCHAI_ROOT)
            dest_dir = base_dir / "hpcsuite_registry" / "hostmachine_reg" / os_arch / os_dist
            dest_dir.mkdir(parents=True, exist_ok=True)

            extracted_dir = dest_dir / openchai_version

            # ── Already installed? ────────────────────────────────────────
            if extracted_dir.is_dir():
                _log(job_id, f"✔  Registry already present: {openchai_version}")
            elif tarball_url:
                tar_path = dest_dir / tarball_name
                await _download_tarball(tarball_url, tar_path, job_id, verify_ssl)
                _extract_tarball(tar_path, dest_dir, job_id)
            else:
                _log(job_id, "⚠  No URL provided and version not locally installed")

            # ── Validate ─────────────────────────────────────────────────
            if extracted_dir.is_dir():
                _log(job_id, f"✅ Registry validated: {extracted_dir}")
            else:
                _log(job_id, f"⚠  Expected directory not found: {extracted_dir}")

            # ── Update config files ───────────────────────────────────────
            if update_configs:
                _log(job_id, "\n── Updating configuration files ──")
                _update_all_yml(
                    base_dir=base_dir,
                    openchai_version=openchai_version,
                    os_label=os_label,
                    os_arch=os_arch,
                    rhel_label=rhel_label,
                    el_label=el_label,
                    kernel=kernel,
                    job_id=job_id,
                )
                _update_ansible_cfg(base_dir, job_id)

            _finish(job_id, "success",
                    result={"openchai_version": openchai_version,
                            "registry_path": str(extracted_dir)},
                    msg="✅ CHAI Release setup complete!")

        except Exception as exc:
            _finish(job_id, "failed", msg=f"❌ Setup failed: {exc}")
            logger.exception("execute_release job %s failed", job_id)

    asyncio.create_task(_worker())
    return job_id


# ─────────────────────────────────────────────────────────────────────────────
# Container image registry  (mirrors container_img_selector.py)
# ─────────────────────────────────────────────────────────────────────────────

async def list_container_tools() -> List[str]:
    return CONTAINER_TOOLS


async def list_container_versions(
    tool: str,
    os_dist: str,
    verify_ssl: Optional[bool] = None,
) -> List[str]:
    """Mirrors _list_versions() from container_img_selector.py."""
    url   = f"{_container_base()}/{os_dist}/{tool}/"
    hrefs = await _fetch_hrefs(url, verify_ssl)
    return sorted({
        h.rstrip("/") for h in hrefs
        if h.endswith("/") and h not in ("../", "./")
        and re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*/$", h)
    })


async def list_container_images(
    tool: str,
    os_dist: str,
    version: str,
    verify_ssl: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """Mirrors _list_images() from container_img_selector.py."""
    base_url = f"{_container_base()}/{os_dist}/{tool}/{version}/"
    hrefs    = await _fetch_hrefs(base_url, verify_ssl)

    images: List[Dict[str, Any]] = []
    for item in hrefs:
        if item in ("../", "./", "/") or item.startswith("?"):
            continue
        if item.endswith("/"):
            # One level of sub-dir
            for sub in await _fetch_hrefs(base_url + item, verify_ssl):
                if _is_image(sub):
                    name = f"{item}{sub}"
                    url  = f"{base_url}{name}"
                    images.append({"name": name, "url": url, "tool": tool, "version": version})
        elif _is_image(item):
            images.append({"name": item, "url": f"{base_url}{item}", "tool": tool, "version": version})

    return images


async def execute_container_download(
    downloads: List[Dict[str, str]],  # [{tool, name, url, version}]
    os_dist: str,
    verify_ssl: Optional[bool],
) -> str:
    """
    Port of container_img_selector.py::_download_file() with resume + retry.
    Returns a job_id for polling.
    """
    job_id = _new_job("container_download", {
        "count": len(downloads), "os_dist": os_dist,
    })

    async def _worker():
        base_dir   = Path(settings.OPENCHAI_ROOT)
        local_root = base_dir / "hpcsuite_registry" / "container_img_reg"
        local_root.mkdir(parents=True, exist_ok=True)

        # Ensure tool sub-dirs exist (mirrors create_local_directories)
        for tool in CONTAINER_TOOLS:
            (local_root / tool).mkdir(exist_ok=True)

        succeeded, skipped, failed = 0, 0, 0

        for dl in downloads:
            tool   = dl.get("tool", "unknown")
            name   = Path(dl.get("name", "")).name
            url    = dl.get("url", "")
            dest   = local_root / tool / name
            tmp    = dest.with_suffix(dest.suffix + ".part")

            if dest.exists() and dest.stat().st_size > 0:
                _log(job_id, f"⏭  Already present, skipping: {name}")
                skipped += 1
                continue

            _log(job_id, f"⬇  Downloading: {name} ({tool})")

            # Retry loop (mirrors MAX_RETRIES=3 in CLI script)
            for attempt in range(1, 4):
                try:
                    resumed = tmp.stat().st_size if tmp.exists() else 0
                    headers_extra: Dict[str, str] = {}
                    if resumed > 0:
                        headers_extra["Range"] = f"bytes={resumed}-"
                        _log(job_id, f"   Resuming from {resumed:,} bytes (attempt {attempt}/3)")

                    async with _build_client(verify_ssl, timeout=600) as http:
                        req_headers = dict(http.headers)
                        req_headers.update(headers_extra)
                        async with http.stream("GET", url, headers=req_headers) as resp:
                            resp.raise_for_status()
                            total      = int(resp.headers.get("content-length", 0))
                            downloaded = resumed
                            last_pct   = -1
                            mode = "ab" if (resumed > 0 and resp.status_code == 206) else "wb"

                            with open(tmp, mode) as fh:
                                async for chunk in resp.aiter_bytes(chunk_size=512 * 1024):
                                    fh.write(chunk)
                                    downloaded += len(chunk)
                                    if total:
                                        pct = int(downloaded / total * 100)
                                        if pct >= last_pct + 10:
                                            _log(job_id, f"   {pct}% ({downloaded // 1_048_576} MB)")
                                            last_pct = pct

                    tmp.rename(dest)
                    _log(job_id, f"✅ Downloaded: {name}")
                    succeeded += 1
                    break
                except Exception as exc:
                    _log(job_id, f"⚠  Attempt {attempt}/3 failed: {exc}")
                    if attempt < 3:
                        await asyncio.sleep(2 ** attempt)
            else:
                tmp.unlink(missing_ok=True)
                _log(job_id, f"❌ Failed after 3 attempts: {name}")
                failed += 1

        summary = (
            f"\n{'='*50}\n"
            f"  Container downloads complete\n"
            f"  ✅ {succeeded} downloaded  ⏭ {skipped} skipped  ❌ {failed} failed\n"
            f"{'='*50}"
        )
        _finish(
            job_id,
            "success" if failed == 0 else "partial",
            result={"succeeded": succeeded, "skipped": skipped, "failed": failed},
            msg=summary,
        )

    asyncio.create_task(_worker())
    return job_id
