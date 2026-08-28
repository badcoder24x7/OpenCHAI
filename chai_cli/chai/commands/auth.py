"""chai auth — login / logout / whoami / status (wraps /auth/*)."""

from __future__ import annotations

import getpass
import time

import click

from ..config import clear_token, load_config, save_config
from ..output import call, render, success


@click.group(name="auth")
def auth_group():
    """Authenticate against the OpenCHAI backend (Linux/PAM credentials)."""


@auth_group.command("login")
@click.option("-u", "--username", prompt=True, help="Linux username on the OpenCHAI host")
@click.option("-p", "--password", default=None, help="Password (omit to be prompted securely)")
@click.pass_context
def login(ctx, username, password):
    """Log in and save the session token locally (~/.config/chai/config.json)."""
    if password is None:
        password = getpass.getpass("Password: ")

    client = ctx.obj.client
    data = call(client.post, "/auth/login", json_body={"username": username, "password": password})

    cfg = load_config()
    cfg.update(
        {
            "base_url": client.base_url,
            "token": data["access_token"],
            "username": data["username"],
            "display_name": data.get("display_name"),
            "role": data.get("role"),
            "groups": data.get("groups", []),
            "token_saved_at": int(time.time()),
            "expires_in": data.get("expires_in"),
        }
    )
    save_config(cfg)
    success(f"Logged in as {data['username']} (role: {data.get('role')}). Token saved.")


@auth_group.command("logout")
@click.pass_context
def logout(ctx):
    """Discard the locally saved session token."""
    client = ctx.obj.client
    if client.token:
        try:
            client.post("/auth/logout")
        except Exception:
            pass  # best-effort — clearing the local token is what actually matters
    clear_token()
    success("Logged out. Local token cleared.")


@auth_group.command("whoami")
@click.pass_context
def whoami(ctx):
    """Show the currently authenticated user."""
    data = call(ctx.obj.client.get, "/auth/me")
    render(data, ctx.obj.output)


@auth_group.command("status")
@click.pass_context
def status(ctx):
    """Show backend auth configuration. Public endpoint — no login required."""
    data = call(ctx.obj.client.get, "/auth/status")
    render(data, ctx.obj.output)
