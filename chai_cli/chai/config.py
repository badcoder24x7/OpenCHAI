"""
CHAI CLI — Local configuration
───────────────────────────────
Stores the backend base URL and the saved session token (from `chai auth
login`) in a small JSON file, by default at ~/.config/chai/config.json.

Precedence used by cli.py when resolving base_url / token:
    1. --base-url / --token CLI flags
    2. CHAI_API_URL / CHAI_TOKEN environment variables
    3. Values saved in the config file
    4. Built-in default (http://127.0.0.1:8000)

The config file contains a bearer token, so it is written with 0600
permissions.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

_TOKEN_FIELDS = (
    "token",
    "username",
    "display_name",
    "role",
    "groups",
    "token_saved_at",
    "expires_in",
)


def config_dir() -> Path:
    override = os.environ.get("CHAI_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".config" / "chai"


def config_file() -> Path:
    return config_dir() / "config.json"


def load_config() -> Dict[str, Any]:
    f = config_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except (OSError, ValueError):
        return {}


def save_config(data: Dict[str, Any]) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    f = config_file()
    f.write_text(json.dumps(data, indent=2, default=str))
    try:
        os.chmod(f, stat.S_IRUSR | stat.S_IWUSR)  # 0600 — contains a bearer token
    except OSError:
        pass


def update_config(**kwargs: Optional[Any]) -> Dict[str, Any]:
    """Merge non-None kwargs into the saved config and persist it."""
    cfg = load_config()
    cfg.update({k: v for k, v in kwargs.items() if v is not None})
    save_config(cfg)
    return cfg


def clear_token() -> None:
    """Remove saved session/token data, keeping base_url / verify_ssl intact."""
    cfg = load_config()
    for k in _TOKEN_FIELDS:
        cfg.pop(k, None)
    save_config(cfg)
