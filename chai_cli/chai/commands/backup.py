"""chai backup — manage automatic backups of mutated config files (/backup/*)."""

from __future__ import annotations

import click

from ..output import call, render, success


@click.group(name="backup")
def backup_group():
    """Manage automatic backups created before mutating file writes."""


@backup_group.command("list")
@click.option("--file", "file_path", default=None, help="Filter backups for a specific original file path")
@click.pass_context
def list_backups(ctx, file_path):
    """List backup entries."""
    data = call(ctx.obj.client.get, "/backup/list", params={"file_path": file_path})
    render(data, ctx.obj.output)


@backup_group.command("read")
@click.argument("backup_path")
@click.pass_context
def read(ctx, backup_path):
    """Print the content of a backup file."""
    data = call(ctx.obj.client.get, "/backup/read", params={"backup_path": backup_path})
    click.echo(data.get("content", ""))


@backup_group.command("restore")
@click.argument("backup_path")
@click.option("--yes", is_flag=True)
@click.pass_context
def restore(ctx, backup_path, yes):
    """Restore a backup file to its original location."""
    if not yes:
        click.confirm(f"Restore '{backup_path}' over its original file?", abort=True)
    data = call(ctx.obj.client.post, "/backup/restore", json_body={"backup_path": backup_path})
    success(data.get("message", "Restored."))
    render(data, ctx.obj.output)


@backup_group.command("delete")
@click.argument("backup_path")
@click.option("--yes", is_flag=True)
@click.pass_context
def delete(ctx, backup_path, yes):
    """Delete a specific backup file."""
    if not yes:
        click.confirm(f"Delete backup '{backup_path}'?", abort=True)
    data = call(ctx.obj.client.delete, "/backup/delete", json_body={"backup_path": backup_path})
    success(data.get("message", "Deleted."))
