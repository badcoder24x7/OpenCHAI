"""chai deploy — run deployments against the current cluster state (/deploy/*)."""

from __future__ import annotations

import click

from ..output import call, render, success
from .playbooks import parse_vars


@click.group(name="deploy")
def deploy_group():
    """Run deployments against the current cluster state (config + nodes)."""


@deploy_group.command("start")
@click.option("--playbook", required=True, help="Playbook path, absolute or relative to the playbook library")
@click.option("--var", "vars_", multiple=True, help="Extra var KEY=VALUE, repeatable")
@click.option("--limit", default=None)
@click.option("--tags", default=None, help="Comma-separated Ansible tags")
@click.option("--dry-run", is_flag=True)
@click.option("--watch", is_flag=True, help="Stream live output after starting (requires the 'websockets' package)")
@click.pass_context
def start(ctx, playbook, vars_, limit, tags, dry_run, watch):
    """Start a deployment.

    Requires a cluster config + at least one node to already exist —
    see `chai cluster create` and `chai nodes add`.
    """
    body = {
        "playbook": playbook,
        "dry_run": dry_run,
        "extra_vars": parse_vars(vars_) or None,
        "tags": [t.strip() for t in tags.split(",")] if tags else None,
        "limit": limit,
    }
    data = call(ctx.obj.client.post, "/deploy/start", json_body=body)
    success(f"Job started: {data['job_id']}")
    render(data, ctx.obj.output)
    if watch:
        from .logs import _follow_job
        _follow_job(ctx, data["job_id"])


@deploy_group.command("generate")
@click.pass_context
def generate(ctx):
    """Generate inventory + group_vars from cluster state without running a playbook."""
    data = call(ctx.obj.client.post, "/deploy/generate")
    success(data.get("message", "Generated."))
    render(data, ctx.obj.output)


@deploy_group.command("jobs")
@click.pass_context
def jobs(ctx):
    """List all deployment jobs."""
    data = call(ctx.obj.client.get, "/deploy/jobs")
    render(data, ctx.obj.output)


@deploy_group.command("job")
@click.argument("job_id")
@click.pass_context
def job(ctx, job_id):
    """Get status of a specific job."""
    data = call(ctx.obj.client.get, f"/deploy/jobs/{job_id}")
    render(data, ctx.obj.output)
