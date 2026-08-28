"""
OpenCHAI GUI — Cluster Setup Wizard Routes  (v4)

Architecture
────────────
Reads from  OPENCHAI_ROOT/cluster_setup/  (set via CLUSTER_SETUP_DIR env var).

  cluster_setup/
  ├── ha_server_setup/          ← setup type
  │   ├── headnode/             ← node role
  │   │   ├── headnode.yml
  │   │   └── pxe_server.yml
  │   ├── hpc_master/
  │   │   ├── ha_master.yml
  │   │   └── pcs_drbd.yml
  │   ├── hpc_management/
  │   │   └── mgmtnodes.yml
  │   ├── hpc_login/
  │   │   └── loginnodes.yml
  │   └── bmcnode/
  └── single_server/            ← setup type (flat — no sub-dirs)
      └── single-master-node.yml

Key design
──────────
• Setup type  = top-level sub-directory
• Node role   = second-level sub-directory (or the type dir itself if flat)
• Playbooks   = all *.yml inside a role directory
• Variables   = extracted live from selected playbook YAMLs (no all.yml loading)
• Inventory   = same priority resolution as the rest of the backend
• Execution   = same ansible_runner service used by every other module

Preserved from v3 (unchanged, kept for backward-compat)
────────────────────────────────────────────────────────
• GET  /types              (now returns cluster_setup/ dirs, not hardcoded list)
• GET  /nodes              (unchanged)
• POST /validate           (unchanged)
• POST /run                (payload extended; old fields still accepted)
• GET  /vars/load          (unchanged — still reads group_vars/)
• GET  /vars/all           (unchanged)
• POST /vars/update        (unchanged)
• POST /vars/add-var       (unchanged)
• DELETE /vars/delete-var  (unchanged)
• POST /run-single         (unchanged)
• /templates/*             (unchanged)

New in v4
─────────
• GET  /{setup_type}/roles
• GET  /{setup_type}/{role_id}/playbooks
• GET  /{setup_type}/{role_id}/playbook-detail?playbook_path=...
• GET  /{setup_type}/{role_id}/multi-playbook-vars?paths=...
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from services.ansible_runner import run_playbook, wait_for_job, get_job, cancel_job_by_id
from services.backup_service import backup_and_write
from services.inventory_def_service import read_inventory_def

router = APIRouter()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# CONFIG HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _cluster_setup_dir() -> str:
    """Return CLUSTER_SETUP_DIR, falling back to OPENCHAI_ROOT/cluster_setup."""
    return settings.CLUSTER_SETUP_DIR or ""


def _ansible_dir() -> str:
    return settings.ANSIBLE_DIR or ""


def _resolve_inventory(ansible_dir: str = "") -> Optional[str]:
    """Priority-ordered inventory resolution (same as rest of backend)."""
    adir = ansible_dir or _ansible_dir()
    if not adir:
        return None
    candidates = [
        os.path.join(adir, "inventory", "inventory_def.txt"),
        os.path.join(adir, "inventory", "inventory_def.py"),
        os.path.join(adir, "inventory", "inventory.sh"),
        os.path.join(adir, "inventory", "hosts.ini"),
        os.path.join(adir, "inventory", "hosts"),
    ]
    for c in candidates:
        if os.path.exists(c):
            logger.info("Resolved inventory: %s", c)
            return c
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PLAYBOOK PARSER  (same logic as playbook_parser service — inline here so
#                   cluster_setup module stays self-contained)
# ─────────────────────────────────────────────────────────────────────────────

_SENSITIVE_KW = {"password", "secret", "token", "key", "pass", "pwd"}

# Phase name hints retained from v3 — used only by /phases (backward-compat)
_PHASE_HINTS = [
    (0, "pre",        "Pre-Requisite Configuration"),
    (0, "bootstrap",  "Pre-Requisite Configuration"),
    (0, "security",   "Pre-Requisite Configuration"),
    (1, "ha",         "High Availability"),
    (1, "provision",  "High Availability"),
    (2, "network",    "Network Configuration"),
    (3, "container",  "Container Environment"),
    (4, "install",    "Software Installation"),
    (5, "configure",  "Configuration"),
    (6, "service",    "Services"),
    (7, "monitor",    "Monitoring"),
    (7, "storage",    "Storage"),
    (8, "hpc",        "HPC Applications"),
]


def _dir_to_phase(dirname: str) -> tuple:
    dl = dirname.lower()
    for pid, hint, name in _PHASE_HINTS:
        if hint in dl:
            return pid, name
    return 99, dirname.replace("_", " ").title()


def _extract_vars(pb_path: str) -> Dict[str, Any]:
    """Extract vars block from a playbook YAML."""
    try:
        with open(pb_path) as fh:
            raw = yaml.safe_load(fh) or []
    except Exception:
        return {}
    extracted: Dict[str, Any] = {}
    if isinstance(raw, list):
        for play in raw:
            if not isinstance(play, dict):
                continue
            for k, v in (play.get("vars") or {}).items():
                extracted[k] = v
            for task in (play.get("tasks") or []):
                if not isinstance(task, dict):
                    continue
                for k, v in (task.get("vars") or {}).items():
                    if k not in extracted:
                        extracted[k] = v
    return extracted


# ── Human-readable label generation ──────────────────────────────────────────
# Abbreviation expansions applied after splitting on underscores so that
# technical shorthand is turned into plain English for the Variables form.
_LABEL_ABBREVS = {
    "fw":        "Firewall",
    "nfs":       "NFS",
    "ntp":       "NTP",
    "ssh":       "SSH",
    "ssl":       "SSL",
    "tls":       "TLS",
    "ip":        "IP",
    "ib":        "InfiniBand",
    "mpi":       "MPI",
    "hpc":       "HPC",
    "url":       "URL",
    "urls":      "URLs",
    "dir":       "Directory",
    "dirs":      "Directories",
    "src":       "Source",
    "dest":      "Destination",
    "cfg":       "Config",
    "conf":      "Config",
    "svc":       "Service",
    "pkg":       "Package",
    "pkgs":      "Packages",
    "repo":      "Repository",
    "repos":     "Repositories",
    "pw":        "Password",
    "pwd":       "Password",
    "passwd":    "Password",
    "auth":      "Auth",
    "mgmt":      "Management",
    "iface":     "Interface",
    "nic":       "Network Interface",
    "bmc":       "BMC",
    "os":        "OS",
    "rpm":       "RPM",
    "rpms":      "RPMs",
    "num":       "Number",
    "max":       "Max",
    "min":       "Min",
    "timeout":   "Timeout",
    "enabled":   "Enabled",
    "disabled":  "Disabled",
    "state":     "State",
    "mode":      "Mode",
    "name":      "Name",
    "names":     "Names",
    "path":      "Path",
    "paths":     "Paths",
    "port":      "Port",
    "ports":     "Ports",
    "user":      "User",
    "users":     "Users",
    "group":     "Group",
    "groups":    "Groups",
    "host":      "Host",
    "hosts":     "Hosts",
    "server":    "Server",
    "servers":   "Servers",
    "client":    "Client",
    "clients":   "Clients",
    "key":       "Key",
    "keys":      "Keys",
    "file":      "File",
    "files":     "Files",
    "log":       "Log",
    "logs":      "Logs",
    "version":   "Version",
    "install":   "Install",
    "setup":     "Setup",
    "missing":   "Missing",
    "override":  "Override",
    "if":        "If",
    "selinux":   "SELinux",
    "vip":       "VIP",
    "drbd":      "DRBD",
    "pcs":       "PCS",
    "ldap":      "LDAP",
    "vlan":      "VLAN",
    "dns":       "DNS",
    "pv":        "PV",
}

# Phase/file prefixes stripped before humanising (e.g. "phase1_0_" → "")
import re as _re
_PHASE_PREFIX_RE = _re.compile(r"^phase\d+[._]\d+[._]?", _re.IGNORECASE)


def _humanize_var_name(name: str) -> str:
    """
    Convert a snake_case Ansible variable name to a human-readable label.

    Examples
    --------
    fw_service_state        → Firewall Service State
    selinux_mode            → SELinux Mode
    ansible_ssh_port        → SSH Port
    nfs_server_ip           → NFS Server IP
    repo_server_url         → Repository Server URL
    fw_install_if_missing   → Firewall Install If Missing
    base_dir                → Base Directory
    """
    # Strip leading phase prefix (e.g. phase1_0_)
    clean = _PHASE_PREFIX_RE.sub("", name)

    # Split on underscores
    tokens = [t for t in clean.split("_") if t]

    # Expand abbreviations or title-case each token
    parts = []
    for tok in tokens:
        lower = tok.lower()
        if lower in _LABEL_ABBREVS:
            parts.append(_LABEL_ABBREVS[lower])
        else:
            parts.append(tok.capitalize())

    return " ".join(parts)


def _flatten_search_keys(value: Any, _depth: int = 0) -> List[str]:
    """
    Recursively collect every key name found inside a variable's value, at
    any nesting depth, so that search can find e.g. "device" inside:

        drbd_nodes:
          - name: master01
            device: /dev/drbd0

    even though "drbd_nodes" is rendered as a single YAML field in the form.
    Depth-limited defensively against unexpected recursive/self-referential
    YAML structures.
    """
    if _depth > 8:
        return []
    keys: List[str] = []
    if isinstance(value, dict):
        for k, v in value.items():
            keys.append(str(k))
            keys.extend(_flatten_search_keys(v, _depth + 1))
    elif isinstance(value, list):
        for item in value:
            keys.extend(_flatten_search_keys(item, _depth + 1))
    return keys


def _normalize_for_search(text: str) -> str:
    """
    Normalizes formatting differences (underscores, hyphens, casing, extra
    whitespace) so that a search for "server ip" matches a field named
    "server_ip", and vice versa.
    """
    return re.sub(r"[\s_\-]+", " ", text.lower()).strip()


def _flatten_search_values(value: Any, _depth: int = 0) -> List[str]:
    """
    Recursively collect every leaf scalar value found inside a variable's
    value, at any nesting depth, so search can match on values (e.g.
    "/hpc_container_pv") as well as keys and labels.
    """
    if _depth > 8:
        return []
    out: List[str] = []
    if isinstance(value, dict):
        for v in value.values():
            out.extend(_flatten_search_values(v, _depth + 1))
    elif isinstance(value, list):
        for item in value:
            out.extend(_flatten_search_values(item, _depth + 1))
    elif value is not None and not isinstance(value, bool):
        out.append(str(value))
    return out


def _vars_to_fields(vars_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    fields = []
    for name, default in vars_dict.items():
        sensitive = any(kw in name.lower() for kw in _SENSITIVE_KW)

        if sensitive:
            ftype        = "password"
            display_val  = "" if default is None else default
        elif isinstance(default, bool):
            ftype        = "boolean"
            display_val  = default
        elif isinstance(default, (int, float)) and not isinstance(default, bool):
            ftype        = "number"
            display_val  = default
        elif isinstance(default, list):
            # Lists of dicts (e.g. nfs_exports) → "yaml" type rendered as a
            # read-only textarea so the user can see/edit the structured value
            # without it being mistaken for a plain comma-separated string.
            if default and isinstance(default[0], dict):
                ftype       = "yaml"
                display_val = yaml.dump(default, default_flow_style=False).rstrip()
            else:
                # Plain scalar list (e.g. required_packages, nameservers) —
                # a distinct "list" type (not "text") so the frontend knows
                # to split this back into a real array on submit, for ANY
                # list-shaped variable, not just ones on a hardcoded name
                # allowlist.
                ftype       = "list"
                display_val = ", ".join(str(v) for v in default)
        elif isinstance(default, dict):
            # Structured dict → "yaml" type, rendered as a textarea
            ftype       = "yaml"
            display_val = yaml.dump(default, default_flow_style=False).rstrip()
        elif default is None:
            ftype        = "text"
            display_val  = ""
        else:
            ftype        = "text"
            display_val  = default

        # Search indexing — match simultaneously against:
        #   1. the raw variable name (e.g. "hpc_container_pv_dir")
        #   2. its generated UI label (e.g. "HPC Container PV Directory") —
        #      this is what lets a search for "Directory" find a field
        #      whose raw key only says "_dir"
        #   3. every key nested inside its value, at any depth, in both
        #      raw and humanized form (dicts, lists, lists of dicts)
        #   4. every leaf value nested inside it, at any depth — but never
        #      for sensitive/password fields
        # All normalized so underscore/hyphen/case differences never
        # prevent a match. The editable "default" shown to the user is
        # unchanged — this is purely additive, so existing playbooks keep
        # working exactly as before.
        label        = _humanize_var_name(name)
        nested_keys  = _flatten_search_keys(default)
        nested_labels = [_humanize_var_name(k) for k in nested_keys]
        nested_values = [] if sensitive else _flatten_search_values(default)
        search_text  = _normalize_for_search(" ".join([
            name, label, *nested_keys, *nested_labels, *nested_values,
        ]))

        fields.append({
            "name":        name,
            "type":        ftype,
            "default":     display_val,
            "sensitive":   sensitive,
            "label":       label,
            "search_text": search_text,
        })
    return fields


def _parse_playbook_meta(pb_path: str) -> Dict[str, Any]:
    try:
        with open(pb_path) as fh:
            raw = yaml.safe_load(fh) or []
    except Exception:
        raw = []

    play_name = os.path.splitext(os.path.basename(pb_path))[0].replace("_", " ").title()
    hosts_opts: List[str] = []

    if isinstance(raw, list):
        for play in raw:
            if not isinstance(play, dict):
                continue
            if "name" in play:
                play_name = play["name"]
            hv = play.get("hosts", "all")
            if isinstance(hv, str):
                hosts_opts = [h.strip() for h in hv.split(",")]
            elif isinstance(hv, list):
                hosts_opts = list(hv)

    extracted = _extract_vars(pb_path)
    return {
        "name":        play_name,
        "file":        os.path.basename(pb_path),
        "full_path":   pb_path,
        "hosts":       hosts_opts or ["all"],
        "vars":        extracted,
        "form_fields": _vars_to_fields(extracted),
    }


# ─────────────────────────────────────────────────────────────────────────────
# FILESYSTEM SCANNING
# ─────────────────────────────────────────────────────────────────────────────

_ROLE_LABEL_MAP = {
    "headnode":        ("Head Node",            "Primary cluster head node"),
    "hpc_master":      ("HPC Master",            "HA master — Pacemaker / DRBD"),
    "hpc_management":  ("HPC Management Node",  "Management / service nodes"),
    "hpc_login":       ("HPC Login Node",        "User login / access nodes"),
    "bmcnode":         ("BMC Node",              "Baseboard Management Controller"),
    "single_server":   ("Single Server",         "All-in-one standalone setup"),
}

_SETUP_TYPE_MAP = {
    "ha_server_setup": ("ha",     "High Availability Server Setup",
                        "Production HA HPC cluster — Pacemaker + DRBD redundancy"),
    "single_server":   ("single", "Single Server Setup",
                        "Standalone HPC master — suitable for development or small clusters"),
}


def _scan_playbooks_in_dir(directory: str, base: str = "") -> List[Dict[str, Any]]:
    """
    Collect all *.yml files in a directory recursively.
    A playbook is marked optional=True if its filename contains "optional".
    Optional playbooks are NOT pre-selected by default in the UI.
    """
    results = []
    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for fname in sorted(files):
            if not fname.endswith((".yml", ".yaml")):
                continue
            if fname.endswith((".bk", ".orig", ".backup")):
                continue
            fp       = os.path.join(root, fname)
            is_opt   = "optional" in fname.lower()
            results.append({
                "name":      fname,
                "full_path": fp,
                "rel_path":  os.path.relpath(fp, base or directory),
                "optional":  is_opt,
            })
    return results


def _get_setup_types() -> List[Dict[str, Any]]:
    base = _cluster_setup_dir()
    if not base or not os.path.isdir(base):
        return []
    types = []
    for dname in sorted(os.listdir(base)):
        dpath = os.path.join(base, dname)
        if not os.path.isdir(dpath):
            continue
        sid, label, desc = _SETUP_TYPE_MAP.get(
            dname, (dname, dname.replace("_", " ").title(), "")
        )
        types.append({
            "id":          sid,
            "dir_name":    dname,
            "label":       label,
            "description": desc,
            "path":        dpath,
        })
    return types


def _resolve_type_dir(setup_type_id: str) -> Optional[str]:
    """Resolve setup type id (e.g. 'ha') → actual directory path."""
    for t in _get_setup_types():
        if t["id"] == setup_type_id:
            return t["path"]
    return None


def _get_roles(setup_type_id: str) -> List[Dict[str, Any]]:
    type_path = _resolve_type_dir(setup_type_id)
    if not type_path:
        return []

    sub_dirs = [
        d for d in os.listdir(type_path)
        if os.path.isdir(os.path.join(type_path, d))
    ]

    roles = []
    if sub_dirs:
        # Multi-role layout (ha_server_setup)
        for dname in sorted(sub_dirs):
            rdpath = os.path.join(type_path, dname)
            label, desc = _ROLE_LABEL_MAP.get(
                dname, (dname.replace("_", " ").title(), "")
            )
            pbs = _scan_playbooks_in_dir(rdpath)
            roles.append({
                "id":             dname,
                "label":          label,
                "description":    desc,
                "path":           rdpath,
                "playbook_count": len(pbs),
            })
    else:
        # Flat layout (single_server) — type dir IS the role
        for t in _get_setup_types():
            if t["id"] == setup_type_id:
                dname = t["dir_name"]
                break
        else:
            dname = setup_type_id
        label, desc = _ROLE_LABEL_MAP.get(
            dname, (dname.replace("_", " ").title(), "")
        )
        pbs = _scan_playbooks_in_dir(type_path)
        roles.append({
            "id":             dname,
            "label":          label,
            "description":    desc,
            "path":           type_path,
            "playbook_count": len(pbs),
        })
    return roles


def _get_role_path(setup_type_id: str, role_id: str) -> Optional[str]:
    type_path = _resolve_type_dir(setup_type_id)
    if not type_path:
        return None
    role_path = os.path.join(type_path, role_id)
    if os.path.isdir(role_path):
        return role_path
    # Flat layout
    return type_path


def _security_check(path: str) -> bool:
    """Ensure path stays inside cluster_setup directory."""
    cs = _cluster_setup_dir()
    if not cs:
        return True
    return os.path.abspath(path).startswith(os.path.abspath(cs))


# ─────────────────────────────────────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────────────────────────────────────

class VarUpdateRequest(BaseModel):
    file_name:  str
    variables:  Dict[str, Any]
    backup:     bool = True


class VarAddRequest(BaseModel):
    file_name:  str
    key:        str
    value:      Any
    backup:     bool = True


class VarDeleteRequest(BaseModel):
    file_name:  str
    key:        str
    backup:     bool = True


class RunRequest(BaseModel):
    # v4 fields
    setup_type:      str                      = "ha"
    role_id:         Optional[str]            = None
    playbook_paths:  Optional[List[str]]      = None   # absolute full paths (v4) OR rel paths (v3)
    limit:           Optional[str]            = None
    dry_run:         bool                     = False
    verbosity:       int                      = 0
    extra_vars:      Optional[Dict[str, Any]] = None
    # v3 backward-compat fields
    phase_ids:       Optional[List[int]]      = None


class SingleRunRequest(BaseModel):
    # Accepts the same shape as RunRequest so the frontend uses one payload format.
    # playbook_paths: list with ONE absolute path (v4) or one rel path (v3).
    playbook_paths:  Optional[List[str]]      = None
    setup_type:      str                      = "ha"
    role_id:         Optional[str]            = None
    limit:           Optional[str]            = None
    dry_run:         bool                     = False
    verbosity:       int                      = 0
    extra_vars:      Optional[Dict[str, Any]] = None


class ValidateRequest(BaseModel):
    variables: Dict[str, Any]


class TemplateSaveRequest(BaseModel):
    name:        str
    description: Optional[str] = ""
    variables:   Dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# ── V4 WIZARD ROUTES ─────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/types", summary="List setup types discovered from cluster_setup/")
async def get_types():
    """
    Returns setup types from CLUSTER_SETUP_DIR.
    Falls back gracefully — returns empty list if directory not found.
    """
    cs_dir = _cluster_setup_dir()
    types  = _get_setup_types()
    return {
        "types":             types,
        "cluster_setup_dir": cs_dir,
        "exists":            os.path.isdir(cs_dir) if cs_dir else False,
    }


@router.get("/{setup_type}/roles", summary="List node roles for a setup type")
async def get_roles(setup_type: str):
    cs_dir = _cluster_setup_dir()
    if not cs_dir or not os.path.isdir(cs_dir):
        raise HTTPException(
            status_code=503,
            detail=f"cluster_setup directory not found: {cs_dir or '(CLUSTER_SETUP_DIR not set)'}",
        )
    roles = _get_roles(setup_type)
    return {"setup_type": setup_type, "roles": roles, "total": len(roles)}


@router.get("/{setup_type}/{role_id}/playbooks", summary="List playbooks for a role")
async def get_role_playbooks(setup_type: str, role_id: str):
    role_path = _get_role_path(setup_type, role_id)
    if not role_path:
        raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")
    playbooks = _scan_playbooks_in_dir(role_path)
    return {
        "setup_type": setup_type,
        "role_id":    role_id,
        "playbooks":  playbooks,
        "total":      len(playbooks),
    }


@router.get("/{setup_type}/{role_id}/playbook-detail",
            summary="Parse vars from a single playbook file")
async def get_playbook_detail(setup_type: str, role_id: str, playbook_path: str):
    if not os.path.exists(playbook_path):
        raise HTTPException(status_code=404, detail=f"Playbook not found: {playbook_path}")
    if not _security_check(playbook_path):
        raise HTTPException(status_code=403, detail="Path outside cluster_setup directory.")
    return _parse_playbook_meta(playbook_path)


@router.get("/{setup_type}/{role_id}/multi-playbook-vars",
            summary="Merged vars from multiple selected playbooks")
async def get_multi_playbook_vars(setup_type: str, role_id: str, paths: str):
    """
    `paths` = comma-separated absolute full_paths.
    Returns per-playbook form fields AND a merged deduplicated set.
    """
    raw_paths = [p.strip() for p in paths.split(",") if p.strip()]
    result: List[Dict] = []
    merged_vars: Dict[str, Any] = {}

    for pb_path in raw_paths:
        if not os.path.exists(pb_path):
            continue
        if not _security_check(pb_path):
            continue
        meta = _parse_playbook_meta(pb_path)
        result.append(meta)
        for k, v in meta["vars"].items():
            if k not in merged_vars:
                merged_vars[k] = v

    return {
        "playbooks":     result,
        "merged_vars":   merged_vars,
        "merged_fields": _vars_to_fields(merged_vars),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ── V3 BACKWARD-COMPAT ROUTES (preserved unchanged) ──────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{setup_type}/phases", summary="[v3] Dynamically discovered phases + playbooks")
async def get_phases(setup_type: str):
    """
    V3 phase discovery from playbook_library/.
    Preserved for backward compatibility.
    """
    base = settings.PLAYBOOK_LIBRARY
    if not base or not os.path.isdir(base):
        return []

    phase_map: Dict[int, Dict] = {}
    auto_id = 50

    for dname in sorted(os.listdir(base)):
        dpath = os.path.join(base, dname)
        if not os.path.isdir(dpath):
            continue

        pid, pname = _dir_to_phase(dname)
        if pid == 99:
            pid = auto_id
            auto_id += 1

        if pid not in phase_map:
            phase_map[pid] = {
                "id":          pid,
                "name":        pname,
                "description": f"Playbooks from {dname}/",
                "directories": [],
                "playbooks":   [],
            }

        phase_map[pid]["directories"].append(dname)

        for root, _, files in os.walk(dpath):
            for fname in sorted(files):
                if not fname.endswith((".yml", ".yaml")):
                    continue
                full = os.path.join(root, fname)
                rel  = os.path.relpath(full, base)
                phase_map[pid]["playbooks"].append({
                    "name":      fname,
                    "rel_path":  rel,
                    "full_path": full,
                    "directory": dname,
                    "exists":    True,
                })

    return sorted(phase_map.values(), key=lambda p: p["id"])


# ── Variables (v3, unchanged) ─────────────────────────────────────────────────

@router.get("/vars/load", summary="Load all group_vars files")
async def load_vars():
    gv_dir = settings.GROUP_VARS_DIR
    if not gv_dir or not os.path.isdir(gv_dir):
        return {"files": {}, "directory": gv_dir, "count": 0}
    files: Dict[str, Any] = {}
    for fname in sorted(os.listdir(gv_dir)):
        if not fname.endswith((".yml", ".yaml")):
            continue
        fpath = os.path.join(gv_dir, fname)
        try:
            with open(fpath) as fh:
                raw = fh.read()
            data = yaml.safe_load(raw) or {}
            files[fname] = {"path": fpath, "variables": data, "raw": raw, "error": None}
        except yaml.YAMLError as e:
            files[fname] = {"path": fpath, "variables": {}, "raw": "", "error": str(e)}
    return {"files": files, "directory": gv_dir, "count": len(files)}


@router.get("/vars/all", summary="Merged flat view of all group_vars")
async def get_all_vars():
    gv_dir = settings.GROUP_VARS_DIR
    merged: Dict[str, Any] = {}
    sources: Dict[str, str] = {}
    if gv_dir and os.path.isdir(gv_dir):
        for fname in sorted(os.listdir(gv_dir)):
            if not fname.endswith((".yml", ".yaml")):
                continue
            fpath = os.path.join(gv_dir, fname)
            try:
                with open(fpath) as fh:
                    data = yaml.safe_load(fh) or {}
                for k, v in data.items():
                    merged[k] = v
                    sources[k] = fname
            except Exception:
                pass
    return {"variables": merged, "sources": sources, "total": len(merged)}


@router.post("/vars/update", summary="Update variables in a group_vars file")
async def update_vars(req: VarUpdateRequest):
    gv_dir = settings.GROUP_VARS_DIR
    if not gv_dir:
        raise HTTPException(status_code=500, detail="GROUP_VARS_DIR not configured.")
    fpath = os.path.join(gv_dir, req.file_name)
    existing: Dict[str, Any] = {}
    if os.path.exists(fpath):
        with open(fpath) as fh:
            existing = yaml.safe_load(fh) or {}
    existing.update(req.variables)
    content = (
        f"# OpenCHAI GUI — group_vars/{req.file_name}\n"
        f"# Auto-managed — last updated via Cluster Setup GUI\n\n"
        + yaml.dump(existing, default_flow_style=False, sort_keys=True)
    )
    bak = backup_and_write(fpath, content, enabled=req.backup)
    return {"message": f"{req.file_name} updated.", "file": fpath,
            "backup_path": bak, "variables": existing}


@router.post("/vars/add-var", summary="Add a variable to a group_vars file")
async def add_var(req: VarAddRequest):
    return await update_vars(VarUpdateRequest(
        file_name=req.file_name,
        variables={req.key: req.value},
        backup=req.backup,
    ))


@router.delete("/vars/delete-var", summary="Remove a variable from a group_vars file")
async def delete_var(req: VarDeleteRequest):
    gv_dir = settings.GROUP_VARS_DIR
    if not gv_dir:
        raise HTTPException(status_code=500, detail="GROUP_VARS_DIR not configured.")
    fpath = os.path.join(gv_dir, req.file_name)
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"{req.file_name} not found.")
    with open(fpath) as fh:
        data = yaml.safe_load(fh) or {}
    if req.key not in data:
        raise HTTPException(status_code=404, detail=f"Variable '{req.key}' not found.")
    del data[req.key]
    content = (
        f"# OpenCHAI GUI — group_vars/{req.file_name}\n\n"
        + yaml.dump(data, default_flow_style=False, sort_keys=True)
    )
    bak = backup_and_write(fpath, content, enabled=req.backup)
    return {"message": f"Variable '{req.key}' removed.", "backup_path": bak}


# ── Job Status + Cancel ───────────────────────────────────────────────────────

#@router.get("/jobs/{job_id}", summary="Get status of a cluster-setup job")
#async def get_job_status(job_id: str):
#    """Returns the current status and metadata of a job launched by /run or /run-single."""
#    job = get_job(job_id)
#    if not job:
#        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
#    return job

@router.get("/jobs/{job_id}", summary="Get status of a cluster-setup job")
async def get_job_status(job_id: str):
    """Returns the current status and metadata of a job launched by /run or /run-single."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@router.post("/jobs/{job_id}/cancel", summary="Cancel a running cluster-setup job")
async def cancel_job(job_id: str):
    """
    Sends SIGTERM to the running ansible-playbook process for this job.
    The process has 5 s to clean up; if it does not exit, SIGKILL is sent.
    Safe to call on an already-finished job (returns 200 with current status).
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.get("status") != "running":
        return {"message": f"Job is not running (status: {job.get('status')}).", "job": job}
    cancelled = await cancel_job_by_id(job_id)
    if cancelled:
        return {"message": f"Job {job_id} cancelled.", "job_id": job_id}
    raise HTTPException(status_code=500, detail="Failed to cancel job.")


# ── Execution ─────────────────────────────────────────────────────────────────

@router.post("/run", summary="Execute playbooks (v4 cluster_setup/ paths OR v3 playbook_library)")
async def run_setup(req: RunRequest):
    """
    Unified execution endpoint.
    - v4: req.playbook_paths contains absolute full_paths from cluster_setup/
    - v3: req.playbook_paths contains relative paths from playbook_library/
          or req.phase_ids selects phases from playbook_library/
    """
    ansible_dir = _ansible_dir()
    if not ansible_dir or not os.path.isdir(ansible_dir):
        raise HTTPException(status_code=500, detail=f"ANSIBLE_DIR not found: {ansible_dir}")

    inv = _resolve_inventory(ansible_dir)
    if not inv:
        raise HTTPException(
            status_code=400,
            detail=(
                "No inventory found. Ensure one of these exists:\n"
                "  inventory/inventory_def.txt\n"
                "  inventory/inventory_def.py\n"
                "  inventory/hosts.ini"
            ),
        )

    playbooks_to_run: List[str] = []

    if req.playbook_paths:
        for p in req.playbook_paths:
            # v4: absolute path inside cluster_setup/
            if os.path.isabs(p) and os.path.exists(p):
                if _security_check(p):
                    playbooks_to_run.append(p)
                else:
                    logger.warning("Path outside cluster_setup/, skipping: %s", p)
            else:
                # v3: relative path inside playbook_library/
                full = os.path.join(settings.PLAYBOOK_LIBRARY or "", p)
                if os.path.exists(full):
                    playbooks_to_run.append(full)
                else:
                    logger.warning("Playbook not found, skipping: %s", full)
    else:
        # v3 phase-based fallback
        phases = await get_phases(req.setup_type)
        for phase in phases:
            if req.phase_ids is not None and phase["id"] not in req.phase_ids:
                continue
            for pb in phase.get("playbooks", []):
                if pb.get("exists"):
                    playbooks_to_run.append(pb["full_path"])

    if not playbooks_to_run:
        raise HTTPException(
            status_code=400,
            detail="No playbooks to execute. Check playbook paths and CLUSTER_SETUP_DIR / PLAYBOOK_LIBRARY.",
        )

    ansible_cfg  = os.path.join(ansible_dir, "ansible.cfg")
    jobs_launched = []

    # ── Sequential execution ──────────────────────────────────────────────────
    # Playbooks have phase-ordered dependencies (e.g. firewall → SELinux →
    # Docker → xCAT/DRBD).  Execute them one at a time and stop on the first
    # failure so downstream phases don't run against a broken environment.
    for pb_path in playbooks_to_run:
        jid = await run_playbook(
            playbook_path=pb_path,
            inventory_path=inv,
            ansible_cfg=ansible_cfg,
            extra_vars=req.extra_vars,
            limit=req.limit,
            dry_run=req.dry_run,
            verbosity=req.verbosity,
            ansible_user=settings.ANSIBLE_USER,
            ssh_key=settings.ANSIBLE_PRIVATE_KEY,
        )
        job_record = {
            "job_id":   jid,
            "playbook": os.path.basename(pb_path),
            "path":     pb_path,
        }
        jobs_launched.append(job_record)
        logger.info("Launched job %s for %s", jid, pb_path)

        # Wait for this job to complete before proceeding to the next playbook.
        # This enforces strict phase-by-phase ordering and prevents dependency
        # failures caused by concurrent / out-of-order execution.
        try:
            finished = await wait_for_job(jid)
            job_record["status"] = finished.get("status", "unknown")
            if finished.get("status") == "failed" and not req.dry_run:
                logger.warning(
                    "Playbook %s failed (job %s) — halting sequential execution.",
                    os.path.basename(pb_path), jid,
                )
                return {
                    "message":     f"Execution halted: playbook '{os.path.basename(pb_path)}' failed. "
                                   f"{len(jobs_launched) - 1} prior job(s) succeeded.",
                    "jobs":        jobs_launched,
                    "dry_run":     req.dry_run,
                    "limit":       req.limit,
                    "inventory":   inv,
                    "ansible_dir": ansible_dir,
                    "halted":      True,
                }
        except TimeoutError:
            logger.error("Job %s timed out waiting for completion", jid)
            job_record["status"] = "timeout"

    return {
        "message":     f"{len(jobs_launched)} job(s) completed sequentially.",
        "jobs":        jobs_launched,
        "dry_run":     req.dry_run,
        "limit":       req.limit,
        "inventory":   inv,
        "ansible_dir": ansible_dir,
        "halted":      False,
    }


@router.post("/run-single", summary="Execute a single playbook (v4 absolute path or v3 rel path)")
async def run_single(req: SingleRunRequest):
    """
    Runs ONE playbook and returns immediately with the job_id so the frontend
    can open a WebSocket for live log streaming.

    Accepts the same payload shape as /run (playbook_paths list) so the
    frontend does not need to know two different field names.
    """
    ansible_dir = _ansible_dir()
    if not ansible_dir or not os.path.isdir(ansible_dir):
        raise HTTPException(status_code=500, detail=f"ANSIBLE_DIR not found: {ansible_dir}")

    inv = _resolve_inventory(ansible_dir)
    if not inv:
        raise HTTPException(status_code=400, detail="No inventory file found.")

    # Resolve the single playbook path
    pb_full = None
    paths   = req.playbook_paths or []
    if paths:
        p = paths[0]
        if os.path.isabs(p) and os.path.exists(p):
            # v4 — absolute path from cluster_setup/
            if _security_check(p):
                pb_full = p
            else:
                raise HTTPException(status_code=400, detail=f"Path outside allowed dirs: {p}")
        else:
            # v3 — relative path inside playbook_library/
            candidate = os.path.join(settings.PLAYBOOK_LIBRARY or "", p)
            if os.path.exists(candidate):
                pb_full = candidate

    if not pb_full:
        raise HTTPException(
            status_code=404,
            detail=f"Playbook not found. Received paths: {paths}",
        )

    ansible_cfg = os.path.join(ansible_dir, "ansible.cfg")
    jid = await run_playbook(
        playbook_path=pb_full,
        inventory_path=inv,
        ansible_cfg=ansible_cfg,
        extra_vars=req.extra_vars,
        limit=req.limit,
        dry_run=req.dry_run,
        verbosity=req.verbosity,
        ansible_user=settings.ANSIBLE_USER,
        ssh_key=settings.ANSIBLE_PRIVATE_KEY,
    )
    return {
        "jobs":      [{"job_id": jid, "playbook": os.path.basename(pb_full), "path": pb_full}],
        "job_id":    jid,
        "playbook":  os.path.basename(pb_full),
        "dry_run":   req.dry_run,
        "limit":     req.limit,
        "inventory": inv,
        "halted":    False,
        "message":   f"Job launched. Stream logs at /logs/ws/{jid}",
    }


# ── Nodes ─────────────────────────────────────────────────────────────────────

@router.get("/nodes", summary="Nodes and groups from inventory_def.txt")
async def get_nodes():
    nodes  = read_inventory_def()
    groups = sorted({n.get("group", "") for n in nodes if n.get("group")})
    return {"nodes": nodes, "groups": groups}


# ── Validate ──────────────────────────────────────────────────────────────────

@router.post("/validate", summary="Validate variables before execution")
async def validate_vars(req: ValidateRequest):
    errors:   List[str] = []
    warnings: List[str] = []

    # Matches a Jinja2 expression, e.g. "{{ primary_ldap_node_ip }}". These
    # are resolved by Ansible at runtime — exactly like the CLI — so the GUI
    # must not try to validate their literal text as a plain IP/hostname or
    # port number. This is what let phase6.1_authentication_ldap.yml's
    # primary_ldap_server_ip / secondary_ldap_server_ip (whose values are
    # Jinja lookups, not literal addresses) fail GUI-only validation before.
    jinja_expr_re = re.compile(r"\{\{.*\}\}")

    for key, val in req.variables.items():
        if val == "" or val is None:
            warnings.append(f"'{key}' is empty.")
            continue

        # Word-boundary key match (not substring) for every heuristic below,
        # so a variable like `vip_resource_name` — which contains "ip" only
        # as part of "vip", not as its own word — is never mistaken for an
        # IP/address/hostname field. This was the exact cause of
        # phase2.1_pcs_drbd.yml's vip_resource_name ("vip_xCAT") being
        # rejected by the GUI for containing an underscore, even though it
        # is a Pacemaker resource name, not an address, and the CLI never
        # applied this check to it at all.
        key_words = set(re.split(r"[_\-\s]+", key.lower()))

        if key_words & {"ip", "addr", "address", "host", "hostname"} and isinstance(val, str) and val:
            if not jinja_expr_re.search(val):
                looks_like_ip       = re.match(r"^\d{1,3}(\.\d{1,3}){3}$", val)
                looks_like_hostname = re.match(r"^[a-zA-Z0-9]([a-zA-Z0-9\-\.]*[a-zA-Z0-9])?$", val)
                if not looks_like_ip and not looks_like_hostname:
                    errors.append(f"'{key}' = '{val}' doesn't look like a valid IP/hostname.")

        # Use the same word-boundary key match for "port" so that fields like
        # nfs_exports, transport, report, etc. (which contain "port" as a
        # substring) are not wrongly validated as TCP/UDP port numbers. Also
        # skip Jinja2-templated values here for the same reason as above.
        if "port" in key_words and val not in ("", None) and not (isinstance(val, str) and jinja_expr_re.search(val)):
            try:
                p = int(val)
                if not (1 <= p <= 65535):
                    errors.append(f"'{key}' port {p} out of range.")
            except (ValueError, TypeError):
                errors.append(f"'{key}' should be a port number (1-65535), got: {val}")
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


# ── Templates (v3, unchanged) ─────────────────────────────────────────────────

def _tmpl_dir() -> str:
    d = (
        os.path.join(settings.OPENCHAI_ROOT, "chai_gui", "backend", "logs", "templates")
        if settings.OPENCHAI_ROOT
        else ""
    )
    if d:
        os.makedirs(d, exist_ok=True)
    return d


@router.get("/templates")
async def list_templates():
    d = _tmpl_dir()
    if not d or not os.path.isdir(d):
        return []
    out = []
    for f in sorted(os.listdir(d)):
        if f.endswith(".json"):
            try:
                with open(os.path.join(d, f)) as fh:
                    out.append(json.load(fh))
            except Exception:
                pass
    return out


@router.post("/templates/save")
async def save_template(req: TemplateSaveRequest):
    d = _tmpl_dir()
    if not d:
        raise HTTPException(status_code=500, detail="OPENCHAI_ROOT not set.")
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.name)
    with open(os.path.join(d, f"{name}.json"), "w") as fh:
        json.dump({"name": req.name, "description": req.description,
                   "variables": req.variables}, fh, indent=2)
    return {"message": f"Profile '{req.name}' saved."}


@router.post("/templates/load/{name}")
async def load_template(name: str):
    d = _tmpl_dir()
    safe  = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    fpath = os.path.join(d, f"{safe}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found.")
    with open(fpath) as fh:
        return json.load(fh)


@router.delete("/templates/{name}")
async def delete_template(name: str):
    d     = _tmpl_dir()
    safe  = re.sub(r"[^a-zA-Z0-9_\-]", "_", name)
    fpath = os.path.join(d, f"{safe}.json")
    if not os.path.exists(fpath):
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found.")
    os.unlink(fpath)
    return {"message": f"Profile '{name}' deleted."}
