"""
OpenCHAI GUI - Playbook Parser Service
Dynamically scans playbook_library/, reads YAML, and extracts:
  - Directory categories (no hardcoding)
  - vars / vars_files blocks
  - Task-level set_fact vars
Returns structured data consumed by the frontend to build dynamic forms.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import yaml

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Directory scan (dynamic — no hardcoding)
# ---------------------------------------------------------------------------

def list_categories() -> List[Dict[str, Any]]:
    """
    Scan playbook_library/ and return a list of category objects.
    Each directory under playbook_library/ becomes one category.
    """
    base = settings.PLAYBOOK_LIBRARY
    if not base or not os.path.isdir(base):
        return []

    categories: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(base)):
        full = os.path.join(base, name)
        if not os.path.isdir(full):
            continue
        playbooks = _scan_playbooks_in_dir(full)
        categories.append({
            "name":      name,
            "path":      full,
            "playbooks": playbooks,
            "count":     len(playbooks),
        })
    return categories


def list_playbooks_in_category(category: str) -> List[Dict[str, Any]]:
    """Return all playbooks inside a specific category directory."""
    base = settings.PLAYBOOK_LIBRARY
    cat_dir = os.path.join(base, category)
    if not os.path.isdir(cat_dir):
        return []
    return _scan_playbooks_in_dir(cat_dir)


def get_playbook_detail(category: str, playbook_name: str) -> Dict[str, Any]:
    """
    Parse a single playbook YAML and return its metadata + extracted vars.
    """
    base = settings.PLAYBOOK_LIBRARY

    # Support nested paths like "container/docker-engine/install.yml"
    pb_path = os.path.join(base, category, playbook_name)
    if not os.path.exists(pb_path):
        # Try flat path as fallback
        pb_path = os.path.join(base, category, playbook_name + ".yml")
    if not os.path.exists(pb_path):
        raise FileNotFoundError(f"Playbook not found: {pb_path}")

    return _parse_playbook(pb_path, base)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _scan_playbooks_in_dir(directory: str) -> List[Dict[str, Any]]:
    """Walk a single directory and collect playbook metadata."""
    base = settings.PLAYBOOK_LIBRARY
    results: List[Dict[str, Any]] = []

    for root, dirs, files in os.walk(directory):
        dirs.sort()
        for fname in sorted(files):
            if not (fname.endswith(".yml") or fname.endswith(".yaml")):
                continue
            full = os.path.join(root, fname)
            rel_to_library = os.path.relpath(full, base)
            rel_to_dir = os.path.relpath(full, directory)
            results.append({
                "name":             fname,
                "rel_path":         rel_to_library,   # used as playbook arg
                "display_path":     rel_to_dir,
                "full_path":        full,
            })
    return results


def _parse_playbook(pb_path: str, library_base: str) -> Dict[str, Any]:
    """Read a playbook YAML file and extract vars for form generation."""
    rel_path = os.path.relpath(pb_path, library_base)

    try:
        with open(pb_path) as fh:
            raw = yaml.safe_load(fh) or []
    except yaml.YAMLError as exc:
        logger.warning("YAML parse error in %s: %s", pb_path, exc)
        raw = []

    extracted_vars: Dict[str, Any] = {}
    hosts_options: List[str] = []
    play_name = os.path.basename(pb_path)

    if isinstance(raw, list):
        for play in raw:
            if not isinstance(play, dict):
                continue

            # Play name
            if "name" in play:
                play_name = play["name"]

            # hosts field
            hosts_val = play.get("hosts", "all")
            if isinstance(hosts_val, str):
                hosts_options = [h.strip() for h in hosts_val.split(",")]
            elif isinstance(hosts_val, list):
                hosts_options = hosts_val

            # Top-level vars block
            for k, v in (play.get("vars") or {}).items():
                extracted_vars[k] = v

            # vars in tasks (set_fact, debug msg, etc.)
            for task in play.get("tasks") or []:
                if not isinstance(task, dict):
                    continue
                for k, v in (task.get("vars") or {}).items():
                    if k not in extracted_vars:
                        extracted_vars[k] = v

    # Build form field descriptors
    form_fields = _vars_to_form_fields(extracted_vars)

    return {
        "name":         play_name,
        "file":         os.path.basename(pb_path),
        "rel_path":     rel_path,
        "full_path":    pb_path,
        "hosts":        hosts_options or ["all"],
        "vars":         extracted_vars,
        "form_fields":  form_fields,
    }


def _flatten_search_keys(value: Any, _depth: int = 0) -> List[str]:
    """
    Recursively collect every key name found inside a variable's value, at
    any nesting depth (dicts, lists, and lists of dicts), so search can find
    a nested key even though the parent var is rendered as one form field.
    Mirrors routes/cluster_setup.py's _flatten_search_keys (kept as a
    separate copy since this module is intentionally self-contained).
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
    """Formatting-insensitive search text: case, underscores, hyphens, whitespace."""
    return re.sub(r"[\s_\-]+", " ", text.lower()).strip()


def _flatten_search_values(value: Any, _depth: int = 0) -> List[str]:
    """Recursively collect every leaf scalar value at any nesting depth."""
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


def _vars_to_form_fields(vars_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert extracted vars dict into a list of form field descriptors."""
    fields: List[Dict[str, Any]] = []
    SENSITIVE_KEYWORDS = {"password", "secret", "token", "key", "pass", "pwd"}

    for name, default in vars_dict.items():
        field_type = "text"
        sensitive = any(kw in name.lower() for kw in SENSITIVE_KEYWORDS)
        label = name.replace("_", " ").title()

        # Computed from the *original* default, before it gets flattened
        # into a display string below, so nested dict/list keys/values are
        # still captured for search even though the displayed value is a
        # string. Sensitive fields never index their value.
        nested_keys   = _flatten_search_keys(default)
        nested_labels = [k.replace("_", " ").title() for k in nested_keys]
        nested_values = [] if sensitive else _flatten_search_values(default)
        search_text = _normalize_for_search(" ".join([
            name, label, *nested_keys, *nested_labels, *nested_values,
        ]))

        if sensitive:
            field_type = "password"
        elif isinstance(default, bool):
            field_type = "boolean"
        elif isinstance(default, int):
            field_type = "number"
        elif isinstance(default, list):
            # Distinct "list" type (not "text") so the frontend reconstructs
            # a real array on submit for ANY list-shaped variable, instead
            # of depending on a hardcoded name allowlist.
            field_type = "list"
            default = ",".join(str(v) for v in default)
        elif isinstance(default, dict):
            field_type = "yaml"
            default = yaml.dump(default, default_flow_style=False).rstrip()

        fields.append({
            "name":        name,
            "type":        field_type,
            "default":     "" if default is None else default,
            "sensitive":   sensitive,
            "label":       label,
            "search_text": search_text,
        })

    return fields
