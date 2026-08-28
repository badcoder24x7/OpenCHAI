"""chai health — node health checks (/nodes/health/*)."""

from __future__ import annotations

import click

from ..output import call, render


@click.group(name="health")
def health_group():
    """Check SSH reachability / basic facts for cluster-state nodes."""


@health_group.command("all")
@click.pass_context
def all_nodes(ctx):
    """Check health of all nodes in the cluster state."""
    data = call(ctx.obj.client.get, "/nodes/health/")
    render(data, ctx.obj.output)


@health_group.command("node")
@click.argument("node_id")
@click.pass_context
def one_node(ctx, node_id):
    """Check health of a single node."""
    data = call(ctx.obj.client.get, f"/nodes/health/{node_id}")
    render(data, ctx.obj.output)
