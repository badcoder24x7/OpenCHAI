"""chai cluster — manage the in-memory cluster configuration (/cluster/*)."""

from __future__ import annotations

import json

import click

from ..output import call, render, success


@click.group(name="cluster")
def cluster_group():
    """Manage the cluster configuration used by the setup wizard / deploy flow."""


@cluster_group.command("create")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), default=None,
              help="JSON file with a full ClusterConfig body (see `chai cluster schema`)")
@click.option("--cluster-name", default=None)
@click.option("--description", default=None)
@click.option("--scheduler", type=click.Choice(["slurm", "pbs", "lsf", "none"]), default=None)
@click.option("--headnode-ip", default=None)
@click.option("--management-network", default=None, help="CIDR, e.g. 192.168.1.0/24")
@click.option("--compute-network", default=None)
@click.option("--storage-network", default=None)
@click.option("--fabric", type=click.Choice(["ethernet", "infiniband", "omnipath", "roce"]), default=None)
@click.option("--ansible-user", default=None)
@click.option("--ansible-ssh-key", default=None)
@click.pass_context
def create(ctx, file_path, cluster_name, description, scheduler, headnode_ip,
           management_network, compute_network, storage_network, fabric,
           ansible_user, ansible_ssh_key):
    """Create or replace the cluster configuration.

    Provide either --file with a full JSON body, or the individual flags
    (at minimum --cluster-name, --headnode-ip, --management-network).
    Flags always override matching fields loaded from --file.
    """
    body = {}
    if file_path:
        with open(file_path) as fh:
            body = json.load(fh)

    body.setdefault("network", {})
    if cluster_name:
        body["cluster_name"] = cluster_name
    if description:
        body["description"] = description
    if scheduler:
        body["scheduler"] = scheduler
    if headnode_ip:
        body["headnode_ip"] = headnode_ip
    if ansible_user:
        body["ansible_user"] = ansible_user
    if ansible_ssh_key:
        body["ansible_ssh_key"] = ansible_ssh_key
    if management_network:
        body["network"]["management_network"] = management_network
    if compute_network:
        body["network"]["compute_network"] = compute_network
    if storage_network:
        body["network"]["storage_network"] = storage_network
    if fabric:
        body["network"]["fabric"] = fabric

    if not body.get("cluster_name") or not body.get("headnode_ip") or not body["network"].get("management_network"):
        raise click.UsageError(
            "Missing required fields. Provide --file, or at least "
            "--cluster-name, --headnode-ip and --management-network."
        )

    data = call(ctx.obj.client.post, "/cluster/create", json_body=body)
    success(data.get("message", "Cluster configuration saved."))
    render(data, ctx.obj.output)


@cluster_group.command("get")
@click.pass_context
def get(ctx):
    """Show the current cluster configuration."""
    data = call(ctx.obj.client.get, "/cluster")
    render(data, ctx.obj.output)


@cluster_group.command("preview")
@click.pass_context
def preview(ctx):
    """Show the rendered group_vars/all.yml YAML preview."""
    data = call(ctx.obj.client.get, "/cluster/preview")
    click.echo(data.get("yaml", ""))


@cluster_group.command("state")
@click.pass_context
def state(ctx):
    """Show full cluster state (config + nodes + deployment status)."""
    data = call(ctx.obj.client.get, "/cluster/state")
    render(data, ctx.obj.output)


@cluster_group.command("reset")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset(ctx, yes):
    """Reset all cluster state (config + nodes)."""
    if not yes:
        click.confirm("Reset ALL cluster state (config + nodes)?", abort=True)
    data = call(ctx.obj.client.delete, "/cluster")
    success(data.get("message", "Cluster state reset."))


@cluster_group.command("schema")
def schema():
    """Print an example ClusterConfig JSON body for `cluster create --file`."""
    example = {
        "cluster_name": "my-hpc-cluster",
        "description": "Example cluster",
        "scheduler": "slurm",
        "network": {
            "management_network": "192.168.1.0/24",
            "compute_network": "10.0.0.0/24",
            "storage_network": "10.1.0.0/24",
            "fabric": "ethernet",
            "dns_server": None,
            "ntp_server": None,
        },
        "services": {
            "slurm_enabled": True,
            "slurm_partition_name": "compute",
            "kubernetes_enabled": False,
            "ldap_enabled": False,
            "nfs_enabled": True,
            "nfs_export_path": "/home",
            "monitoring_enabled": True,
            "infiniband_enabled": False,
        },
        "ansible_user": "root",
        "ansible_ssh_key": "~/.ssh/id_rsa",
        "headnode_ip": "192.168.1.10",
    }
    click.echo(json.dumps(example, indent=2))
