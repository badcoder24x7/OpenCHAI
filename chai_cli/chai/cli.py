"""
CHAI CLI — entry point
─────────────────────────
Registers global options (--base-url, --token, --no-verify-ssl, --output)
and wires up every command group. Run `chai --help` for the full list.
"""

from __future__ import annotations

import click

from . import __version__
from .client import ChaiClient
from .config import DEFAULT_BASE_URL, load_config

from .commands import (
    audit,
    auth,
    backup,
    cluster,
    config_cmd,
    deploy,
    health,
    info,
    inventory,
    logs,
    nodes,
    playbooks,
)


class CliContext:
    """Object attached to click.Context.obj — passed to every subcommand."""

    def __init__(self, client: ChaiClient, output: str):
        self.client = client
        self.output = output


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--base-url",
    envvar="CHAI_API_URL",
    default=None,
    help=f"OpenCHAI backend URL. Default: saved config, else {DEFAULT_BASE_URL}",
)
@click.option(
    "--token",
    envvar="CHAI_TOKEN",
    default=None,
    help="Bearer token. Default: token saved by `chai auth login`.",
)
@click.option(
    "--no-verify-ssl",
    is_flag=True,
    default=False,
    help="Disable TLS certificate verification (self-signed backend certs).",
)
@click.option(
    "-o",
    "--output",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format for command results.",
)
@click.version_option(__version__, prog_name="chai")
@click.pass_context
def main(ctx: click.Context, base_url, token, no_verify_ssl, output_format):
    """CHAI — command-line client for the OpenCHAI HPC-AI cluster manager.

    Talks to the same FastAPI backend as the OpenCHAI web GUI, so anything
    done through `chai` is immediately visible in the GUI and vice versa.

    Start with:  chai auth login
    """
    cfg = load_config()
    resolved_base_url = base_url or cfg.get("base_url") or DEFAULT_BASE_URL
    resolved_token = token or cfg.get("token")
    verify_ssl = False if no_verify_ssl else cfg.get("verify_ssl", True)

    client = ChaiClient(base_url=resolved_base_url, token=resolved_token, verify_ssl=verify_ssl)
    ctx.obj = CliContext(client=client, output=output_format)


main.add_command(auth.auth_group, name="auth")
main.add_command(config_cmd.config_group, name="config")
main.add_command(cluster.cluster_group, name="cluster")
main.add_command(nodes.nodes_group, name="nodes")
main.add_command(inventory.inventory_group, name="inventory")
main.add_command(health.health_group, name="health")
main.add_command(playbooks.playbooks_group, name="playbooks")
main.add_command(deploy.deploy_group, name="deploy")
main.add_command(logs.logs_group, name="logs")
main.add_command(backup.backup_group, name="backup")
main.add_command(audit.audit_group, name="audit")
main.add_command(info.info_group, name="info")


if __name__ == "__main__":
    main()
