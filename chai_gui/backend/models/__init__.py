"""
OpenCHAI GUI — Pydantic Models  (v3)
Shared data models used by routes and services.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class NodeRole(str, Enum):
    headnode   = "headnode"
    compute    = "compute"
    gpu        = "gpu"
    storage    = "storage"
    login      = "login"
    management = "management"
    service    = "service"


class NetworkFabric(str, Enum):
    ethernet   = "ethernet"
    infiniband = "infiniband"
    omnipath   = "omnipath"
    roce       = "roce"


class SchedulerType(str, Enum):
    slurm = "slurm"
    pbs   = "pbs"
    lsf   = "lsf"
    none  = "none"


class DeploymentStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed  = "failed"
    dry_run = "dry_run"


# ─────────────────────────────────────────────────────────────────────────────
# Node
# ─────────────────────────────────────────────────────────────────────────────

class NodeBase(BaseModel):
    hostname:    str               = Field(...,  example="cn01")
    ip_address:  str               = Field(...,  example="192.168.1.101")
    role:        NodeRole          = Field(NodeRole.compute)
    bmc_ip:      Optional[str]     = Field(None, example="192.168.2.101")
    mac_address: Optional[str]     = Field(None, example="AA:BB:CC:DD:EE:FF")
    cpu_count:   Optional[int]     = Field(None, example=64)
    ram_gb:      Optional[int]     = Field(None, example=256)
    gpu_count:   Optional[int]     = Field(0,    example=4)
    gpu_model:   Optional[str]     = Field(None, example="A100")
    tags:        Optional[Dict[str, str]] = Field(default_factory=dict)


class NodeCreate(NodeBase):
    pass


class NodeUpdate(BaseModel):
    hostname:    Optional[str]      = None
    ip_address:  Optional[str]      = None
    role:        Optional[NodeRole] = None
    bmc_ip:      Optional[str]      = None
    mac_address: Optional[str]      = None
    cpu_count:   Optional[int]      = None
    ram_gb:      Optional[int]      = None
    gpu_count:   Optional[int]      = None
    gpu_model:   Optional[str]      = None
    tags:        Optional[Dict[str, str]] = None


class Node(NodeBase):
    id: str


# ─────────────────────────────────────────────────────────────────────────────
# Cluster
# ─────────────────────────────────────────────────────────────────────────────

class ServiceConfig(BaseModel):
    slurm_enabled:        bool          = True
    slurm_partition_name: str           = "compute"
    kubernetes_enabled:   bool          = False
    ldap_enabled:         bool          = False
    ldap_server:          Optional[str] = None
    ldap_base_dn:         Optional[str] = None
    nfs_enabled:          bool          = True
    nfs_server:           Optional[str] = None
    nfs_export_path:      str           = "/home"
    monitoring_enabled:   bool          = True
    infiniband_enabled:   bool          = False


class NetworkConfig(BaseModel):
    management_network: str               = Field(..., example="192.168.1.0/24")
    compute_network:    Optional[str]     = Field(None, example="10.0.0.0/24")
    storage_network:    Optional[str]     = Field(None, example="10.1.0.0/24")
    fabric:             NetworkFabric     = NetworkFabric.ethernet
    dns_server:         Optional[str]     = None
    ntp_server:         Optional[str]     = None


class ClusterConfig(BaseModel):
    cluster_name:    str           = Field(..., example="my-hpc-cluster")
    description:     Optional[str] = None
    scheduler:       SchedulerType = SchedulerType.slurm
    network:         NetworkConfig
    services:        ServiceConfig = Field(default_factory=ServiceConfig)
    ansible_user:    str           = "root"
    ansible_ssh_key: str           = "~/.ssh/id_rsa"
    headnode_ip:     str           = Field(..., example="192.168.1.10")


class ClusterState(BaseModel):
    config:            Optional[ClusterConfig] = None
    nodes:             List[Node]              = Field(default_factory=list)
    deployment_status: DeploymentStatus        = DeploymentStatus.pending
    last_deploy_at:    Optional[str]           = None
    last_deploy_log:   Optional[str]           = None


# ─────────────────────────────────────────────────────────────────────────────
# Deployment
# ─────────────────────────────────────────────────────────────────────────────

class DeployRequest(BaseModel):
    playbook:       str                       = Field(..., example="provision/master.yml")
    dry_run:        bool                      = False
    extra_vars:     Optional[Dict[str, Any]]  = None
    tags:           Optional[List[str]]       = None
    limit:          Optional[str]             = None
    vault_password: Optional[str]             = None


class DeployResponse(BaseModel):
    job_id:   str
    status:   DeploymentStatus
    message:  str
    playbook: str
    dry_run:  bool
