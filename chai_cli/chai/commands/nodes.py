"""chai nodes — manage cluster-state nodes (/nodes/*)."""

from __future__ import annotations

import json

import click

from ..output import call, render, success

ROLE_CHOICES = ["headnode", "compute", "gpu", "storage", "login", "management", "service"]


def _parse_tags(tag_tuples):
    tags = {}
    for t in tag_tuples:
        if "=" not in t:
            raise click.BadParameter(f"Tag '{t}' must be in KEY=VALUE form")
        k, v = t.split("=", 1)
        tags[k] = v
    return tags


@click.group(name="nodes")
def nodes_group():
    """Manage nodes in the in-memory cluster state (setup-wizard model)."""


@nodes_group.command("list")
@click.pass_context
def list_nodes(ctx):
    """List all nodes."""
    data = call(ctx.obj.client.get, "/nodes")
    render(data, ctx.obj.output)


@nodes_group.command("get")
@click.argument("node_id")
@click.pass_context
def get_node(ctx, node_id):
    """Get a single node by ID."""
    data = call(ctx.obj.client.get, f"/nodes/{node_id}")
    render(data, ctx.obj.output)


@nodes_group.command("add")
@click.option("--hostname", required=True)
@click.option("--ip", "ip_address", required=True)
@click.option("--role", type=click.Choice(ROLE_CHOICES), default="compute")
@click.option("--bmc-ip", default=None)
@click.option("--mac", "mac_address", default=None)
@click.option("--cpu", "cpu_count", type=int, default=None)
@click.option("--ram-gb", type=int, default=None)
@click.option("--gpu-count", type=int, default=0)
@click.option("--gpu-model", default=None)
@click.option("--tag", "tags", multiple=True, help="KEY=VALUE, repeatable")
@click.pass_context
def add_node(ctx, hostname, ip_address, role, bmc_ip, mac_address, cpu_count,
             ram_gb, gpu_count, gpu_model, tags):
    """Add a node to the cluster state."""
    body = {
        "hostname": hostname,
        "ip_address": ip_address,
        "role": role,
        "bmc_ip": bmc_ip,
        "mac_address": mac_address,
        "cpu_count": cpu_count,
        "ram_gb": ram_gb,
        "gpu_count": gpu_count,
        "gpu_model": gpu_model,
        "tags": _parse_tags(tags),
    }
    data = call(ctx.obj.client.post, "/nodes/add", json_body=body)
    success(f"Node '{data['hostname']}' added (id={data['id']}).")
    render(data, ctx.obj.output)


@nodes_group.command("update")
@click.argument("node_id")
@click.option("--hostname", default=None)
@click.option("--ip", "ip_address", default=None)
@click.option("--role", type=click.Choice(ROLE_CHOICES), default=None)
@click.option("--bmc-ip", default=None)
@click.option("--mac", "mac_address", default=None)
@click.option("--cpu", "cpu_count", type=int, default=None)
@click.option("--ram-gb", type=int, default=None)
@click.option("--gpu-count", type=int, default=None)
@click.option("--gpu-model", default=None)
@click.option("--tag", "tags", multiple=True, help="KEY=VALUE, repeatable (replaces all tags)")
@click.pass_context
def update_node(ctx, node_id, hostname, ip_address, role, bmc_ip, mac_address,
                 cpu_count, ram_gb, gpu_count, gpu_model, tags):
    """Update fields on an existing node. Only provided fields are changed."""
    body = {
        "hostname": hostname,
        "ip_address": ip_address,
        "role": role,
        "bmc_ip": bmc_ip,
        "mac_address": mac_address,
        "cpu_count": cpu_count,
        "ram_gb": ram_gb,
        "gpu_count": gpu_count,
        "gpu_model": gpu_model,
    }
    body = {k: v for k, v in body.items() if v is not None}
    if tags:
        body["tags"] = _parse_tags(tags)
    if not body:
        raise click.UsageError("Provide at least one field to update.")
    data = call(ctx.obj.client.put, f"/nodes/{node_id}", json_body=body)
    success(f"Node '{data['hostname']}' updated.")
    render(data, ctx.obj.output)


@nodes_group.command("delete")
@click.argument("node_id")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_node(ctx, node_id, yes):
    """Delete a node."""
    if not yes:
        click.confirm(f"Delete node '{node_id}'?", abort=True)
    data = call(ctx.obj.client.delete, f"/nodes/{node_id}")
    success(data.get("message", "Deleted."))


@nodes_group.command("bulk-import")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), required=True,
              help="JSON file containing a list of node objects (same shape as `nodes add` flags)")
@click.pass_context
def bulk_import(ctx, file_path):
    """Bulk import nodes from a JSON file (list of node objects)."""
    with open(file_path) as fh:
        nodes_in = json.load(fh)
    if not isinstance(nodes_in, list):
        raise click.UsageError("JSON file must contain a list of node objects.")
    data = call(ctx.obj.client.post, "/nodes/bulk", json_body=nodes_in)
    success(f"Imported {len(data)} node(s).")
    render(data, ctx.obj.output)
