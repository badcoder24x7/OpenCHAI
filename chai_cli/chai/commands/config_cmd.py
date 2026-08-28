"""chai config — manage local CLI configuration (backend URL, TLS)."""

from __future__ import annotations

import click

from ..config import DEFAULT_BASE_URL, config_file, load_config, update_config
from ..output import render, success


@click.group(name="config")
def config_group():
    """Manage local CLI configuration (backend URL, TLS verification)."""


@config_group.command("show")
@click.pass_context
def show(ctx):
    """Show current CLI configuration (token is masked)."""
    cfg = load_config()
    safe = dict(cfg)
    if safe.get("token"):
        safe["token"] = safe["token"][:12] + "...(hidden)"
    safe.setdefault("base_url", DEFAULT_BASE_URL)
    safe["config_file"] = str(config_file())
    render(safe, ctx.obj.output)


@config_group.command("set")
@click.option("--base-url", default=None, help="OpenCHAI backend base URL, e.g. http://cluster-head:8000")
@click.option("--verify-ssl/--no-verify-ssl", "verify_ssl", default=None, help="Enable/disable TLS certificate verification")
def set_config(base_url, verify_ssl):
    """Persist a default backend URL / TLS setting for future commands."""
    cfg = update_config(base_url=base_url, verify_ssl=verify_ssl)
    success(f"Configuration saved to {config_file()}")
    for k, v in cfg.items():
        if k == "token":
            continue
        click.echo(f"  {k}: {v}")
