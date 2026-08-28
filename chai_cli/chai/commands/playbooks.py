"""chai playbooks — browse and execute the Ansible playbook library (/playbooks/*)."""

from __future__ import annotations

import json

import click

from ..output import call, render, success


def parse_vars(var_tuples):
    """Parse repeated --var KEY=VALUE options into a dict, JSON-decoding values when possible."""
    result = {}
    for item in var_tuples:
        if "=" not in item:
            raise click.BadParameter(f"--var '{item}' must be KEY=VALUE")
        k, v = item.split("=", 1)
        try:
            v = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            pass  # keep as a raw string
        result[k] = v
    return result


@click.group(name="playbooks")
def playbooks_group():
    """Browse and execute playbooks from the Ansible playbook library."""


@playbooks_group.command("categories")
@click.pass_context
def categories(ctx):
    """List playbook categories (top-level directories)."""
    data = call(ctx.obj.client.get, "/playbooks/categories")
    render(data, ctx.obj.output)


@playbooks_group.command("list")
@click.argument("category")
@click.pass_context
def list_category(ctx, category):
    """List playbooks inside a category."""
    data = call(ctx.obj.client.get, f"/playbooks/categories/{category}")
    render(data, ctx.obj.output)


@playbooks_group.command("tree")
@click.pass_context
def tree(ctx):
    """Show the full playbook library tree."""
    data = call(ctx.obj.client.get, "/playbooks/tree")
    render(data, ctx.obj.output)


@playbooks_group.command("groups")
@click.pass_context
def groups(ctx):
    """List inventory groups/hostnames available to target."""
    data = call(ctx.obj.client.get, "/playbooks/inventory-groups")
    render(data, ctx.obj.output)


@playbooks_group.command("detail")
@click.argument("category")
@click.argument("playbook_name")
@click.pass_context
def detail(ctx, category, playbook_name):
    """Show parsed variables / form fields for a playbook."""
    data = call(ctx.obj.client.get, f"/playbooks/detail/{category}/{playbook_name}")
    render(data, ctx.obj.output)


@playbooks_group.command("execute")
@click.argument("playbook_rel_path")
@click.option("--var", "vars_", multiple=True, help="Extra var KEY=VALUE, repeatable (JSON-decoded when possible)")
@click.option("--limit", default=None, help="Restrict to a host/group pattern")
@click.option("--tags", default=None, help="Comma-separated Ansible tags")
@click.option("--dry-run", is_flag=True, help="Run in Ansible check mode")
@click.option("--verbosity", type=int, default=0)
@click.option("--watch", is_flag=True, help="Stream live output after starting (requires the 'websockets' package)")
@click.pass_context
def execute(ctx, playbook_rel_path, vars_, limit, tags, dry_run, verbosity, watch):
    """Execute a playbook by path relative to the playbook library, e.g. provision/master.yml"""
    body = {
        "playbook_rel_path": playbook_rel_path,
        "extra_vars": parse_vars(vars_) or None,
        "limit": limit,
        "tags": [t.strip() for t in tags.split(",")] if tags else None,
        "dry_run": dry_run,
        "verbosity": verbosity,
    }
    data = call(ctx.obj.client.post, "/playbooks/execute", json_body=body)
    success(f"Job started: {data['job_id']}")
    render(data, ctx.obj.output)
    if watch:
        from .logs import _follow_job
        _follow_job(ctx, data["job_id"])
