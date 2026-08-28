"""
OpenCHAI GUI - Config Mapper
Maps ClusterConfig fields to Ansible group_vars YAML files.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict

import yaml

from models import ClusterConfig

logger = logging.getLogger(__name__)


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (non-destructive)."""
    result = dict(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def generate_group_vars(config: ClusterConfig, group_vars_dir: str) -> Dict[str, str]:
    """
    Write (or merge with existing) group_vars/all.yml and role-specific
    group_vars files derived from *config*.

    Returns a dict {filename: rendered_yaml_content}.
    """
    os.makedirs(group_vars_dir, exist_ok=True)
    written: Dict[str, str] = {}

    # -----------------------------------------------------------------------
    # all.yml — shared vars
    # -----------------------------------------------------------------------
    all_vars: Dict[str, Any] = {
        "cluster_name": config.cluster_name,
        "headnode_ip": config.headnode_ip,
        "ansible_user": config.ansible_user,
        "ansible_ssh_private_key_file": config.ansible_ssh_key,
        # Scheduler
        "scheduler": config.scheduler.value,
        # Network
        "management_network": config.network.management_network,
        "network_fabric": config.network.fabric.value,
    }
    if config.network.dns_server:
        all_vars["dns_server"] = config.network.dns_server
    if config.network.ntp_server:
        all_vars["ntp_server"] = config.network.ntp_server
    if config.network.compute_network:
        all_vars["compute_network"] = config.network.compute_network
    if config.network.storage_network:
        all_vars["storage_network"] = config.network.storage_network

    # Services
    svc = config.services
    all_vars.update(
        {
            "slurm_enabled": svc.slurm_enabled,
            "slurm_partition_name": svc.slurm_partition_name,
            "kubernetes_enabled": svc.kubernetes_enabled,
            "ldap_enabled": svc.ldap_enabled,
            "nfs_enabled": svc.nfs_enabled,
            "monitoring_enabled": svc.monitoring_enabled,
            "infiniband_enabled": svc.infiniband_enabled,
        }
    )
    if svc.ldap_server:
        all_vars["ldap_server"] = svc.ldap_server
    if svc.ldap_base_dn:
        all_vars["ldap_base_dn"] = svc.ldap_base_dn
    if svc.nfs_server:
        all_vars["nfs_server"] = svc.nfs_server
    all_vars["nfs_export_path"] = svc.nfs_export_path

    written["all.yml"] = _write_group_var(group_vars_dir, "all.yml", all_vars)

    # -----------------------------------------------------------------------
    # slurm.yml  (if SLURM enabled)
    # -----------------------------------------------------------------------
    if svc.slurm_enabled:
        slurm_vars: Dict[str, Any] = {
            "slurm_cluster_name": config.cluster_name,
            "slurm_control_machine": config.headnode_ip,
            "slurm_partition_name": svc.slurm_partition_name,
            "slurm_partition_state": "UP",
        }
        written["slurm.yml"] = _write_group_var(
            group_vars_dir, "slurm.yml", slurm_vars
        )

    # -----------------------------------------------------------------------
    # ldap.yml  (if LDAP enabled)
    # -----------------------------------------------------------------------
    if svc.ldap_enabled and svc.ldap_server:
        ldap_vars: Dict[str, Any] = {
            "ldap_uri": f"ldap://{svc.ldap_server}",
            "ldap_base": svc.ldap_base_dn or "dc=cluster,dc=local",
            "ldap_bind_user": "cn=admin,dc=cluster,dc=local",
        }
        written["ldap.yml"] = _write_group_var(
            group_vars_dir, "ldap.yml", ldap_vars
        )

    # -----------------------------------------------------------------------
    # nfs.yml  (if NFS enabled)
    # -----------------------------------------------------------------------
    if svc.nfs_enabled:
        nfs_vars: Dict[str, Any] = {
            "nfs_server_ip": svc.nfs_server or config.headnode_ip,
            "nfs_export_path": svc.nfs_export_path,
            "nfs_mount_point": svc.nfs_export_path,
            "nfs_opts": "defaults,_netdev",
        }
        written["nfs.yml"] = _write_group_var(group_vars_dir, "nfs.yml", nfs_vars)

    logger.info(
        "group_vars written to %s: %s", group_vars_dir, list(written.keys())
    )
    return written


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_group_var(directory: str, filename: str, data: Dict[str, Any]) -> str:
    path = os.path.join(directory, filename)
    # Merge with existing file so manual edits survive GUI overwrites
    if os.path.exists(path):
        with open(path) as fh:
            existing = yaml.safe_load(fh) or {}
        data = _deep_merge(existing, data)

    content = (
        "# OpenCHAI GUI — auto-generated group_vars\n"
        "# Manual overrides below this block are preserved on re-generation\n\n"
        + yaml.dump(data, default_flow_style=False, sort_keys=True)
    )
    with open(path, "w") as fh:
        fh.write(content)
    return content


def render_yaml_preview(config: ClusterConfig) -> str:
    """Return a YAML preview of what would be written to group_vars/all.yml."""
    all_vars = {
        "cluster_name": config.cluster_name,
        "headnode_ip": config.headnode_ip,
        "scheduler": config.scheduler.value,
        "management_network": config.network.management_network,
        "services": {
            "slurm": config.services.slurm_enabled,
            "kubernetes": config.services.kubernetes_enabled,
            "ldap": config.services.ldap_enabled,
            "nfs": config.services.nfs_enabled,
            "monitoring": config.services.monitoring_enabled,
        },
    }
    return yaml.dump(all_vars, default_flow_style=False, sort_keys=True)
