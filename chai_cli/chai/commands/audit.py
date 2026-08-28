"""chai audit — view the append-only audit trail (/audit)."""

from __future__ import annotations

import click

from ..output import call, render, success


@click.group(name="audit")
def audit_group():
    """View the append-only audit trail of mutating API actions."""


@audit_group.command("list")
@click.option("--limit", type=int, default=100)
@click.option("--action", "action_filter", default=None, help="Filter by action prefix, e.g. node.")
@click.pass_context
def list_entries(ctx, limit, action_filter):
    """List recent audit entries, newest first."""
    data = call(ctx.obj.client.get, "/audit", params={"limit": limit, "action": action_filter})
    render(data, ctx.obj.output)


@audit_group.command("clear")
@click.option("--yes", is_flag=True)
@click.pass_context
def clear(ctx, yes):
    """Clear the audit log (dev/testing only)."""
    if not yes:
        click.confirm("Clear the entire audit log?", abort=True)
    data = call(ctx.obj.client.delete, "/audit")
    success(data.get("message", "Cleared."))
