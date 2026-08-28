"""chai info — inspect resolved OpenCHAI paths and directory structure (/info/*)."""

from __future__ import annotations

import click

from ..output import call, render


@click.group(name="info")
def info_group():
    """Inspect resolved OpenCHAI paths and directory structure."""


@info_group.command("paths")
@click.pass_context
def paths(ctx):
    """Show all resolved OpenCHAI directory paths and whether they exist."""
    data = call(ctx.obj.client.get, "/info/paths")
    render(data, ctx.obj.output)


@info_group.command("tree")
@click.pass_context
def tree(ctx):
    """Top-level directory listing of OPENCHAI_ROOT."""
    data = call(ctx.obj.client.get, "/info/tree")
    render(data, ctx.obj.output)


@info_group.command("ansible")
@click.pass_context
def ansible(ctx):
    """Show the ansible/ directory structure."""
    data = call(ctx.obj.client.get, "/info/ansible")
    render(data, ctx.obj.output)
