"""chai logs — job log polling + live WebSocket streaming (/logs/*, /logtail/*)."""

from __future__ import annotations

import sys

import click

from ..output import call, error, render


@click.group(name="logs")
def logs_group():
    """View and stream job / backend logs."""


@logs_group.command("jobs")
@click.pass_context
def jobs(ctx):
    """List job log summaries."""
    data = call(ctx.obj.client.get, "/logs/jobs")
    render(data, ctx.obj.output)


@logs_group.command("stream")
@click.argument("job_id")
@click.option("--lines", type=int, default=100, help="Number of most recent lines to fetch")
@click.pass_context
def stream(ctx, job_id, lines):
    """Poll and print the last N log lines for a job (one-shot, no live streaming)."""
    data = call(ctx.obj.client.get, f"/logs/stream/{job_id}", params={"lines": lines})
    for line in data.get("lines", []):
        click.echo(line)


@logs_group.command("follow")
@click.argument("job_id")
@click.pass_context
def follow(ctx, job_id):
    """Live-stream a job's output over WebSocket until it finishes."""
    _follow_job(ctx, job_id)


@logs_group.command("tail")
@click.argument("log_name", type=click.Choice(["app", "audit"]))
@click.option("--lines", type=int, default=50, help="Number of historical lines to show on connect")
@click.pass_context
def tail(ctx, log_name, lines):
    """Live-tail a backend log file ('app' or 'audit') over WebSocket."""
    _run_ws_stream(ctx, f"/logtail/{log_name}", query={"lines": lines})


# ---------------------------------------------------------------------------
# Shared WebSocket helpers — also used by `chai playbooks execute --watch`
# and `chai deploy start --watch`.
# ---------------------------------------------------------------------------

def _ws_url(client, path: str) -> str:
    base = client.base_url
    if base.startswith("https://"):
        return "wss://" + base[len("https://"):] + path
    if base.startswith("http://"):
        return "ws://" + base[len("http://"):] + path
    return "ws://" + base + path


def _require_websockets():
    try:
        import websockets  # noqa: F401
        return websockets
    except ImportError:
        error(
            "Live streaming requires the 'websockets' package. Install it with:\n"
            "  pip install 'chai-cli[live]'   (or: pip install websockets)"
        )
        sys.exit(1)


def _run_ws_stream(ctx, path: str, query: dict = None) -> None:
    """Connect to a backend WebSocket path and print every text frame received."""
    import asyncio
    import ssl as ssl_module

    websockets = _require_websockets()
    client = ctx.obj.client

    url = _ws_url(client, path)
    if query:
        qs = "&".join(f"{k}={v}" for k, v in query.items() if v is not None)
        if qs:
            url = f"{url}?{qs}"

    extra_headers = {"Authorization": f"Bearer {client.token}"} if client.token else {}
    ssl_context = None
    if url.startswith("wss://") and not client.verify_ssl:
        ssl_context = ssl_module._create_unverified_context()

    async def _run():
        async with websockets.connect(url, extra_headers=extra_headers, ssl=ssl_context) as ws:
            async for message in ws:
                if message == "__ping__":
                    continue
                if isinstance(message, str) and message.startswith("__done__:"):
                    job_status = message.split(":", 1)[1]
                    click.echo(f"\n--- job finished: {job_status} ---")
                    break
                text = message if isinstance(message, str) else message.decode("utf-8", "replace")
                sys.stdout.write(text if text.endswith("\n") else text + "\n")
                sys.stdout.flush()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\n(detached from stream)")
    except Exception as exc:
        error(f"Live stream error: {exc}")
        sys.exit(1)


def _follow_job(ctx, job_id: str) -> None:
    """Stream a running playbook/deploy job's output to the terminal until it finishes."""
    _run_ws_stream(ctx, f"/logs/ws/{job_id}")
