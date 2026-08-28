"""
OpenCHAI GUI - Smart Ansible Runner Service

Features:
  ✅ NO automatic '-i' inventory injection
  ✅ Uses ansible.cfg default inventory
  ✅ Smart extra-vars normalization
  ✅ Converts comma-separated values into lists
  ✅ Handles network CIDR inputs correctly
  ✅ Supports YAML/JSON string parsing
  ✅ Clean logging
  ✅ WebSocket streaming
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import stat
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import yaml

from config import settings

logger = logging.getLogger(__name__)

JobRecord = Dict[str, Any]

_jobs: Dict[str, JobRecord] = {}
_ws_callbacks: Dict[str, List[Callable]] = {}

# ---------------------------------------------------------------------------
# Variables expected to behave like LISTS
# ---------------------------------------------------------------------------

LIST_LIKE_VARS = {
    "chrony_allow_networks",
    "dns_servers",
    "ntp_servers",
    "allowed_networks",
    "firewall_allowed_networks",
    "nameservers",
    "search_domains",
    "packages",
    "users",
    "groups",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def register_ws_callback(job_id: str, cb: Callable) -> None:
    _ws_callbacks.setdefault(job_id, []).append(cb)


def unregister_ws_callback(job_id: str, cb: Callable) -> None:
    if job_id in _ws_callbacks:
        _ws_callbacks[job_id] = [
            c for c in _ws_callbacks[job_id]
            if c is not cb
        ]


# Keys in the job record that must never be serialised to JSON.
# _proc  = asyncio.subprocess.Process — not JSON-serialisable.
# _*     = any other internal private field added in future.
_INTERNAL_KEYS = {"_proc"}


def _safe_job(job: JobRecord) -> JobRecord:
    """Return a copy of *job* with internal/non-serialisable keys removed."""
    return {k: v for k, v in job.items() if k not in _INTERNAL_KEYS}


def get_job(job_id: str) -> Optional[JobRecord]:
    job = _jobs.get(job_id)
    return _safe_job(job) if job is not None else None


def list_jobs() -> List[JobRecord]:
    return [_safe_job(j) for j in _jobs.values()]


async def cancel_job_by_id(job_id: str) -> bool:
    """
    Send SIGTERM to the ansible-playbook process for *job_id*.
    Waits up to 5 s for graceful exit, then sends SIGKILL.
    Returns True if the process was found and signalled.
    """
    import signal
    job = _jobs.get(job_id)
    if not job:
        return False
    proc = job.get("_proc")
    if proc is None:
        return False
    if proc.returncode is not None:
        # already finished
        return False
    try:
        proc.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        job["status"]      = "cancelled"
        job["finished_at"] = __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat()
        job["log_lines"].append("\n[CANCELLED] Job was cancelled by the user.\n")
        await _emit(job_id, "[CANCELLED] Job was cancelled by the user.")
        logger.info("Job %s cancelled", job_id)
        return True
    except Exception as exc:
        logger.error("Failed to cancel job %s: %s", job_id, exc)
        return False


async def wait_for_job(job_id: str, poll_interval: float = 1.0, timeout: float = 7200.0) -> "JobRecord":
    """
    Wait for a job to reach a terminal status (success / failed).
    Returns the final job record.  Raises TimeoutError after *timeout* seconds.
    Used by the sequential execution path in cluster_setup.
    """
    elapsed = 0.0
    while elapsed < timeout:
        job = _jobs.get(job_id)
        if job and job.get("status") not in ("running", None):
            return job
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


# ---------------------------------------------------------------------------
# Smart extra-vars normalization
# ---------------------------------------------------------------------------

def _normalize_extra_vars(
    extra_vars: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Normalize incoming variables automatically.

    Examples:

      "172.10.3.0/22"
        -> ["172.10.3.0/22"]

      "1.1.1.1,8.8.8.8"
        -> ["1.1.1.1", "8.8.8.8"]

      '["a","b"]'
        -> ["a", "b"]
    """

    normalized: Dict[str, Any] = {}

    for key, value in extra_vars.items():

        # -------------------------------------------------
        # Parse stringified JSON/YAML
        # -------------------------------------------------

        if isinstance(value, str):

            value = value.strip()

            # Parse any stringified JSON/YAML structure. The primary,
            # authoritative fix now lives in the frontend (ClusterSetup.jsx
            # reconstructs real types from each field's backend-provided
            # `type` before ever sending the request) — this stays as a
            # defense-in-depth net for any other caller (e.g. routes/
            # playbooks.py, routes/deploy.py) that doesn't go through that
            # path yet.
            #
            # A multi-line value is attempted regardless of its first
            # character: a YAML *mapping* (e.g. fallback_dns → "nameservers:
            # \n- 10.208.192.11\n...") starts with a bare "key:" line, not
            # "[", "{", or "- " — the previous version of this check only
            # looked for those three, so a dict-shaped textarea value like
            # fallback_dns was silently sent to Ansible as one literal
            # string instead of the {"nameservers": [...], ...} object it
            # needs to be. Guarded by the isinstance(parsed, ...) check
            # below so an ordinary single-line string is never mistakenly
            # rewritten.
            looks_structured = value.startswith(("[", "{", "- ")) or "\n" in value
            if looks_structured:
                try:
                    parsed = yaml.safe_load(value)
                    # Only accept parsed result if it's actually structured
                    if isinstance(parsed, (list, dict)):
                        value = parsed
                except Exception:
                    pass

        # -------------------------------------------------
        # Auto-convert list-like vars
        # -------------------------------------------------

        if key in LIST_LIKE_VARS:

            # Single string -> list
            if isinstance(value, str):

                # comma-separated
                if "," in value:

                    value = [
                        item.strip()
                        for item in value.split(",")
                        if item.strip()
                    ]

                else:
                    value = [value]

            # tuple/set -> list
            elif isinstance(value, (tuple, set)):
                value = list(value)

        normalized[key] = value

    return normalized


# ---------------------------------------------------------------------------
# Core launcher
# ---------------------------------------------------------------------------

async def run_playbook(
    *,
    playbook_path: str,
    inventory_path: str = "",   # intentionally ignored
    ansible_cfg: str = "",
    extra_vars: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None,
    limit: Optional[str] = None,
    dry_run: bool = False,
    verbosity: int = 0,
    ansible_user: str = "root",
    ssh_key: str = "~/.ssh/id_rsa",
    vault_password: Optional[str] = None,
) -> str:

    job_id = str(uuid.uuid4())

    # -------------------------------------------------
    # Working directory
    # -------------------------------------------------

    work_dir = (
        settings.ANSIBLE_DIR
        or os.path.dirname(playbook_path)
    )

    # -------------------------------------------------
    # Normalize extra-vars
    # -------------------------------------------------

    extra_vars = extra_vars or {}
    extra_vars = _normalize_extra_vars(extra_vars)

    logger.info(
        "Normalized extra-vars: %s",
        extra_vars
    )

    # -------------------------------------------------
    # Build command
    # -------------------------------------------------

    cmd: List[str] = [
        "ansible-playbook",
        playbook_path,
    ]

    # -------------------------------------------------
    # Inventory handling
    # -------------------------------------------------
    # DO NOT automatically inject '-i'
    # Uses ansible.cfg default inventory
    # -------------------------------------------------

    if inventory_path:

        logger.warning(
            "inventory_path provided but ignored. "
            "Using ansible.cfg default inventory."
        )

    # -------------------------------------------------
    # User
    # -------------------------------------------------

    cmd += ["--user", ansible_user]

    # -------------------------------------------------
    # SSH key
    # -------------------------------------------------

    expanded_key = os.path.expanduser(ssh_key)

    if os.path.exists(expanded_key):

        cmd += [
            "--private-key",
            expanded_key,
        ]

    else:

        logger.warning(
            "SSH key not found: %s",
            expanded_key
        )

    # -------------------------------------------------
    # Dry run
    # -------------------------------------------------

    if dry_run:
        cmd.append("--check")

    # -------------------------------------------------
    # Verbosity
    # -------------------------------------------------

    if verbosity and 1 <= verbosity <= 4:

        cmd.append(
            "-" + ("v" * verbosity)
        )

    # -------------------------------------------------
    # Extra vars
    # -------------------------------------------------

    if extra_vars:

        cmd += [
            "--extra-vars",
            json.dumps(extra_vars),
        ]

    # -------------------------------------------------
    # Vault password (supplied via the web GUI)
    # -------------------------------------------------
    # ansible.cfg may point vault_password_file at a static path that isn't
    # present on every deployment. Rather than requiring that file to exist
    # on disk, the GUI can collect the password once per run and hand it to
    # ansible-playbook through a short-lived, 600-permission temp file.
    # --vault-password-file on the command line takes precedence over
    # ansible.cfg's setting, and the temp file is deleted as soon as the
    # job finishes (success or failure) in _stream_subprocess's finally
    # block below — it never outlives the run, and never appears in the
    # command line itself (so it can't leak via `ps`).
    vault_pass_file: Optional[str] = None
    if vault_password:
        fd, vault_pass_file = tempfile.mkstemp(prefix=".vault_pass_", text=True)
        try:
            os.chmod(vault_pass_file, stat.S_IRUSR | stat.S_IWUSR)  # 600
            with os.fdopen(fd, "w") as fh:
                fh.write(vault_password)
        except Exception:
            try:
                os.unlink(vault_pass_file)
            except OSError:
                pass
            raise
        cmd += ["--vault-password-file", vault_pass_file]

    # -------------------------------------------------
    # Tags
    # -------------------------------------------------

    if tags:

        cmd += [
            "--tags",
            ",".join(tags),
        ]

    # -------------------------------------------------
    # Limit
    # -------------------------------------------------

    if limit:

        cmd += [
            "--limit",
            limit,
        ]

    # -------------------------------------------------
    # Environment
    # -------------------------------------------------

    env = dict(os.environ)

    # Force ansible.cfg
    if ansible_cfg and os.path.exists(ansible_cfg):

        env["ANSIBLE_CONFIG"] = ansible_cfg

    else:

        cfg_path = os.path.join(
            work_dir,
            "ansible.cfg"
        )

        if os.path.exists(cfg_path):

            env["ANSIBLE_CONFIG"] = cfg_path

    env["ANSIBLE_FORCE_COLOR"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    # -------------------------------------------------
    # Human-readable command
    # -------------------------------------------------

    command_display = shlex.join(cmd)

    # -------------------------------------------------
    # Job record
    # -------------------------------------------------

    _jobs[job_id] = {
        "job_id": job_id,
        "playbook": playbook_path,
        "status": "running",
        "dry_run": dry_run,
        "limit": limit,
        "command": command_display,
        "work_dir": work_dir,
        "inventory": "ansible.cfg default",
        "extra_vars": extra_vars,
        "started_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "finished_at": None,
        "return_code": None,
        "log_lines": [],
    }

    logger.info(
        "Job %s | cwd=%s | cmd=%s",
        job_id,
        work_dir,
        command_display,
    )

    # -------------------------------------------------
    # Launch async subprocess
    # -------------------------------------------------

    asyncio.create_task(
        _stream_subprocess(
            job_id=job_id,
            cmd=cmd,
            env=env,
            cwd=work_dir,
            vault_pass_file=vault_pass_file,
        )
    )

    return job_id


# ---------------------------------------------------------------------------
# Streaming subprocess
# ---------------------------------------------------------------------------

async def _stream_subprocess(
    job_id: str,
    cmd: List[str],
    env: Dict,
    cwd: str,
    vault_pass_file: Optional[str] = None,
) -> None:

    try:
        await _stream_subprocess_inner(job_id=job_id, cmd=cmd, env=env, cwd=cwd)
    finally:
        if vault_pass_file:
            try:
                os.unlink(vault_pass_file)
            except OSError:
                pass


async def _stream_subprocess_inner(
    job_id: str,
    cmd: List[str],
    env: Dict,
    cwd: str,
) -> None:

    job = _jobs[job_id]

    await _emit(
        job_id,
        f"[OpenCHAI] Working directory : {cwd}"
    )

    await _emit(
        job_id,
        f"[OpenCHAI] Command           : {job['command']}"
    )

    await _emit(
        job_id,
        "[OpenCHAI] Inventory         : ansible.cfg default"
    )

    await _emit(job_id, "-" * 60)

    try:

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            cwd=cwd,
        )
        # Store proc reference so cancel_job_by_id can send SIGTERM
        _jobs[job_id]["_proc"] = proc

    except FileNotFoundError:

        await _emit(
            job_id,
            "[ERROR] ansible-playbook not found."
        )

        job.update(
            status="failed",
            return_code=-1,
            finished_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        return

    except Exception as exc:

        await _emit(
            job_id,
            f"[ERROR] Failed to launch process: {exc}"
        )

        job.update(
            status="failed",
            return_code=-1,
            finished_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        return

    # -------------------------------------------------
    # Stream reader
    # -------------------------------------------------

    async def read_stream(stream, prefix=""):

        async for raw in stream:

            line = raw.decode(
                "utf-8",
                errors="replace"
            ).rstrip()

            if line:

                full = (
                    f"{prefix}{line}"
                    if prefix
                    else line
                )

                job["log_lines"].append(full)

                await _emit(job_id, full)

    # -------------------------------------------------
    # Read stdout/stderr concurrently
    # -------------------------------------------------

    await asyncio.gather(
        read_stream(proc.stdout),
        read_stream(proc.stderr, "[STDERR] "),
    )

    await proc.wait()

    rc = proc.returncode

    # -------------------------------------------------
    # Final status
    # -------------------------------------------------

    job["return_code"] = rc

    job["status"] = (
        "success"
        if rc == 0
        else "failed"
    )

    job["finished_at"] = datetime.now(
        timezone.utc
    ).isoformat()

    summary = (
        f"\n{'='*60}\n"
        f" Job {job_id[:8]} | "
        f"{'SUCCESS ✅' if rc == 0 else 'FAILED ❌'} "
        f"| rc={rc}\n"
        f"{'='*60}"
    )

    job["log_lines"].append(summary)

    await _emit(job_id, summary)

    # Sentinel: signals WebSocket handlers that the job stream is complete.
    # The sentinel itself is NOT stored in log_lines so it doesn't appear in
    # the REST polling endpoint or get re-replayed to late-joining clients.
    await _emit(job_id, f"__done__:{job['status']}")

    logger.info(
        "Job %s finished rc=%s status=%s",
        job_id,
        rc,
        job["status"],
    )


# ---------------------------------------------------------------------------
# WebSocket emitter
# ---------------------------------------------------------------------------

async def _emit(
    job_id: str,
    line: str,
) -> None:

    for cb in list(
        _ws_callbacks.get(job_id, [])
    ):

        try:

            await cb(line)

        except Exception as exc:

            logger.debug(
                "WS emit error: %s",
                exc
            )
