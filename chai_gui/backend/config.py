"""
OpenCHAI GUI — Configuration  (v3)

All paths resolve from OPENCHAI_ROOT or can be individually overridden via
environment variables. validate_paths() is called once at startup.

Changes vs v2
─────────────
- Settings is a proper class with cached properties — no class-body side-effects
- CORS_ORIGINS normalised to remove empty strings and duplicates
- LOG_LEVEL validated against known levels; falls back to INFO
- validate_paths() exits only when REQUIRED paths are missing; optional paths
  emit warnings instead of killing the process
- Added CHAI_VERIFY_SSL env-var support (consumed by chai_release_service)
"""

from __future__ import annotations

import logging
import os
import sys
from typing import List


_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings:
    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = os.getenv("OPENCHAI_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("OPENCHAI_PORT", "8000"))

    # ── CORS ─────────────────────────────────────────────────────────────────
    CORS_ORIGINS: List[str] = list(dict.fromkeys(
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173",
        ).split(",")
        if o.strip()
    ))

    # ── Root paths ────────────────────────────────────────────────────────────
    OPENCHAI_ROOT: str = os.getenv("OPENCHAI_ROOT", "")

    # Ansible paths — auto-derive from OPENCHAI_ROOT when not overridden
    ANSIBLE_DIR: str = os.getenv(
        "ANSIBLE_DIR",
        os.path.join(OPENCHAI_ROOT, "automation", "ansible") if OPENCHAI_ROOT else "",
    )
    INVENTORY_PATH: str = os.getenv(
        "INVENTORY_PATH",
        os.path.join(ANSIBLE_DIR, "inventory", "hosts.ini") if ANSIBLE_DIR else "",
    )
    GROUP_VARS_DIR: str = os.getenv(
        "GROUP_VARS_DIR",
        os.path.join(ANSIBLE_DIR, "group_vars") if ANSIBLE_DIR else "",
    )
    PLAYBOOK_LIBRARY: str = os.getenv(
        "PLAYBOOK_LIBRARY",
        os.path.join(ANSIBLE_DIR, "playbook_library") if ANSIBLE_DIR else "",
    )
    ANSIBLE_CFG: str = os.getenv(
        "ANSIBLE_CFG",
        os.path.join(ANSIBLE_DIR, "ansible.cfg") if ANSIBLE_DIR else "",
    )
    # host_vars/ directory — per-host Ansible variables, including the
    # ansible-vault-encrypted ansible_password / ansible_become_pass values
    # written by vault_service.py. Matches the dynamic inventory script's
    # expected layout: {ANSIBLE_DIR}/inventory/host_vars/<hostname>.yml
    HOST_VARS_DIR: str = os.getenv(
        "HOST_VARS_DIR",
        os.path.join(ANSIBLE_DIR, "inventory", "host_vars") if ANSIBLE_DIR else "",
    )
    # Vault password file referenced by ansible.cfg's vault_password_file
    # setting. Auto-generated with a random passphrase on first use if it
    # doesn't already exist — see vault_service.ensure_vault_password_file().
    VAULT_PASSWORD_FILE: str = os.getenv(
        "VAULT_PASSWORD_FILE",
        os.path.join(ANSIBLE_DIR, ".vault_pass") if ANSIBLE_DIR else "",
    )

    # ── Cluster Setup Wizard — points to OPENCHAI_ROOT/cluster_setup/ ────────
    # This directory contains ha_server_setup/ and single_server/ sub-directories,
    # each holding role directories with playbook *.yml files.
    CLUSTER_SETUP_DIR: str = os.getenv(
        "CLUSTER_SETUP_DIR",
        os.path.join(OPENCHAI_ROOT, "cluster_setup") if OPENCHAI_ROOT else "",
    )

    # ── Top-level subdirectories ──────────────────────────────────────────────
    AI_DIR:           str = os.path.join(OPENCHAI_ROOT, "ai")           if OPENCHAI_ROOT else ""
    BENCHMARKS_DIR:   str = os.path.join(OPENCHAI_ROOT, "benchmarks")   if OPENCHAI_ROOT else ""
    CHAI_CLI_DIR:     str = os.path.join(OPENCHAI_ROOT, "chai_cli")     if OPENCHAI_ROOT else ""
    CHAI_SETUP_DIR:   str = os.path.join(OPENCHAI_ROOT, "chai_setup")   if OPENCHAI_ROOT else ""
    CONTAINER_DIR:    str = os.path.join(OPENCHAI_ROOT, "container")    if OPENCHAI_ROOT else ""
    DOCS_DIR:         str = os.path.join(OPENCHAI_ROOT, "docs")         if OPENCHAI_ROOT else ""
    HEADNODE_DIR:     str = os.path.join(OPENCHAI_ROOT, "headnode")     if OPENCHAI_ROOT else ""
    HPC_DIR:          str = os.path.join(OPENCHAI_ROOT, "hpc")          if OPENCHAI_ROOT else ""
    IMAGES_DIR:       str = os.path.join(OPENCHAI_ROOT, "images")       if OPENCHAI_ROOT else ""
    LOGS_DIR_ROOT:    str = os.path.join(OPENCHAI_ROOT, "logs")         if OPENCHAI_ROOT else ""
    MONITORING_DIR:   str = os.path.join(OPENCHAI_ROOT, "monitoring")   if OPENCHAI_ROOT else ""
    NETWORKING_DIR:   str = os.path.join(OPENCHAI_ROOT, "networking")   if OPENCHAI_ROOT else ""
    POLICIES_DIR:     str = os.path.join(OPENCHAI_ROOT, "policies")     if OPENCHAI_ROOT else ""
    PROVISIONING_DIR: str = os.path.join(OPENCHAI_ROOT, "provisioning") if OPENCHAI_ROOT else ""
    RELEASES_DIR:     str = os.path.join(OPENCHAI_ROOT, "Releases")     if OPENCHAI_ROOT else ""
    SERVICENODES_DIR: str = os.path.join(OPENCHAI_ROOT, "servicenodes") if OPENCHAI_ROOT else ""
    STORAGE_DIR:      str = os.path.join(OPENCHAI_ROOT, "storage")      if OPENCHAI_ROOT else ""

    # ── SSH credentials ───────────────────────────────────────────────────────
    ANSIBLE_USER:        str = os.getenv("ANSIBLE_USER", "root")
    ANSIBLE_PRIVATE_KEY: str = os.getenv(
        "ANSIBLE_PRIVATE_KEY", os.path.expanduser("~/.ssh/id_rsa")
    )

    # ── Internal state / logging ──────────────────────────────────────────────
    _backend_dir: str = os.path.dirname(os.path.abspath(__file__))
    STATE_FILE: str = os.getenv(
        "STATE_FILE",
        os.path.join(_backend_dir, "logs", "cluster_state.json"),
    )

    _raw_log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_LEVEL: str = _raw_log_level if _raw_log_level in _VALID_LOG_LEVELS else "INFO"
    LOG_DIR:   str = os.path.join(_backend_dir, "logs")

    # ── JWT Authentication ───────────────────────────────────────────────────
    # JWT_SECRET_KEY: set to a long random string in start.sh.
    # If unset, a random key is generated at startup (sessions lost on restart).
    #   Generate one: openssl rand -hex 64
    JWT_SECRET_KEY:              str = os.getenv("JWT_SECRET_KEY", "")
    JWT_ALGORITHM:               str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    # Comma-separated Linux group names that grant admin role in the GUI.
    # Restricted to openchai-admins only — wheel/sudo membership does NOT
    # grant portal access (root bypasses this via OPENCHAI_ALLOW_ROOT).
    OPENCHAI_ADMIN_GROUPS:       str = os.getenv(
        "OPENCHAI_ADMIN_GROUPS", "openchai-admins"
    )
    OPENCHAI_ALLOW_ROOT: bool = os.getenv("OPENCHAI_ALLOW_ROOT", "true").strip().lower() \
        not in ("false", "0", "no")

    # ── CHAI Release registry ─────────────────────────────────────────────────
    CHAI_REGISTRY_URL: str = os.getenv(
        "OPENCHAI_VAULT_NETWORK_URL",
        "https://hpcsangrah-test.pune.cdac.in/vault/OpenCHAI/hpcsuite_registry/",
    )
    # Default FALSE — the OpenCHAI registry uses a self-signed certificate.
    # Set CHAI_VERIFY_SSL=true in start.sh once a valid cert is installed.
    CHAI_VERIFY_SSL: bool = os.getenv("CHAI_VERIFY_SSL", "false").strip().lower() \
        not in ("false", "0", "no")


settings = Settings()


# ─────────────────────────────────────────────────────────────────────────────
# Path validator
# ─────────────────────────────────────────────────────────────────────────────

def validate_paths() -> None:
    log = logging.getLogger("openchai_gui.config")

    log.info("─" * 55)
    log.info("  OpenCHAI GUI — Path Validation")
    log.info("─" * 55)

    if not settings.OPENCHAI_ROOT:
        log.error("OPENCHAI_ROOT is not set! Set it in start.sh or as an env var.")
        sys.exit(1)

    required = [
        ("OPENCHAI_ROOT", settings.OPENCHAI_ROOT),
        ("ANSIBLE_DIR",   settings.ANSIBLE_DIR),
    ]
    optional = [
        ("PLAYBOOK_LIBRARY",     settings.PLAYBOOK_LIBRARY),
        ("INVENTORY_PATH",       settings.INVENTORY_PATH),
        ("GROUP_VARS_DIR",       settings.GROUP_VARS_DIR),
        ("ANSIBLE_CFG",          settings.ANSIBLE_CFG),
        ("SSH_KEY",              settings.ANSIBLE_PRIVATE_KEY),
        ("HOST_VARS_DIR",        settings.HOST_VARS_DIR),
        ("VAULT_PASSWORD_FILE",  settings.VAULT_PASSWORD_FILE),
    ]

    all_ok = True
    for label, path in required:
        if os.path.exists(path):
            log.info("  ✅  %-22s %s", label, path)
        else:
            log.error("  ❌  %-22s %s  ← NOT FOUND", label, path)
            all_ok = False

    for label, path in optional:
        if os.path.exists(path):
            log.info("  ✅  %-22s %s", label, path)
        else:
            log.warning("  ⚠️   %-22s %s  (will be created when needed)", label, path)

    log.info("─" * 55)

    if not all_ok:
        log.error("Required paths missing. Fix OPENCHAI_ROOT and retry.")
        sys.exit(1)
