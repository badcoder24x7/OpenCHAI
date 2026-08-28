"""chai inventory — manage automation/ansible/inventory/inventory_def.txt (/inventory-def/*).

This is the real inventory consumed by playbook runs — distinct from
`chai nodes`, which manages the in-memory setup-wizard cluster state.
"""

from __future__ import annotations

import click

from ..output import call, render, success


@click.group(name="inventory")
def inventory_group():
    """Manage the real deployment inventory (inventory_def.txt)."""


@inventory_group.command("list")
@click.pass_context
def list_inventory(ctx):
    """List all nodes in inventory_def.txt."""
    data = call(ctx.obj.client.get, "/inventory-def")
    render(data, ctx.obj.output)


@inventory_group.command("add")
@click.option("--hostname", "ansible_hostname", required=True, help="ansible_hostname (inventory key)")
@click.option("--ip", required=True)
@click.option("--user", "ansible_user", default="root")
@click.option("--password", default=None, help="ansible_password (vault-encrypted server-side)")
@click.option("--become-pass", "ansible_become_pass", default=None)
@click.option("--group", default="compute")
@click.option("--fqdn", "hostname", default=None, help="Optional full hostname (defaults to --hostname)")
@click.option("--ssh-port", default="22")
@click.option("--no-backup", is_flag=True, help="Skip auto-backup of inventory_def.txt before writing")
@click.pass_context
def add(ctx, ansible_hostname, ip, ansible_user, password, ansible_become_pass,
         group, hostname, ssh_port, no_backup):
    """Add a node to inventory_def.txt."""
    body = {
        "ansible_hostname": ansible_hostname,
        "ip": ip,
        "ansible_user": ansible_user,
        "ansible_password": password or "",
        "ansible_become_pass": ansible_become_pass or "",
        "group": group,
        "hostname": hostname,
        "ssh_port": ssh_port,
    }
    data = call(ctx.obj.client.post, "/inventory-def/add", json_body=body, params={"backup": not no_backup})
    success(data.get("message", "Node added."))


@inventory_group.command("update")
@click.argument("ansible_hostname")
@click.option("--ip", default=None)
@click.option("--user", "ansible_user", default=None)
@click.option("--password", default=None, help="Set to update; use --clear-password to remove")
@click.option("--clear-password", is_flag=True)
@click.option("--become-pass", "ansible_become_pass", default=None)
@click.option("--clear-become-pass", is_flag=True)
@click.option("--group", default=None)
@click.option("--fqdn", "hostname", default=None)
@click.option("--ssh-port", default=None)
@click.option("--no-backup", is_flag=True)
@click.pass_context
def update(ctx, ansible_hostname, ip, ansible_user, password, clear_password,
           ansible_become_pass, clear_become_pass, group, hostname, ssh_port, no_backup):
    """Update a node in inventory_def.txt. Only provided fields change."""
    body = {"ip": ip, "ansible_user": ansible_user, "group": group, "hostname": hostname, "ssh_port": ssh_port}
    body = {k: v for k, v in body.items() if v is not None}

    if clear_password:
        body["ansible_password"] = ""
    elif password is not None:
        body["ansible_password"] = password

    if clear_become_pass:
        body["ansible_become_pass"] = ""
    elif ansible_become_pass is not None:
        body["ansible_become_pass"] = ansible_become_pass

    if not body:
        raise click.UsageError("Provide at least one field to update.")

    data = call(ctx.obj.client.put, f"/inventory-def/{ansible_hostname}", json_body=body,
                params={"backup": not no_backup})
    success(data.get("message", "Node updated."))


@inventory_group.command("delete")
@click.argument("ansible_hostname")
@click.option("--yes", is_flag=True)
@click.option("--no-backup", is_flag=True)
@click.pass_context
def delete(ctx, ansible_hostname, yes, no_backup):
    """Delete a node from inventory_def.txt (and its vaulted credentials)."""
    if not yes:
        click.confirm(f"Delete inventory node '{ansible_hostname}'?", abort=True)
    data = call(ctx.obj.client.delete, f"/inventory-def/{ansible_hostname}", params={"backup": not no_backup})
    success(data.get("message", "Deleted."))


@inventory_group.command("bulk-import")
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False), required=True,
              help="CSV file (no password column — set credentials individually afterwards)")
@click.option("--no-backup", is_flag=True)
@click.pass_context
def bulk_import(ctx, file_path, no_backup):
    """Bulk import nodes from a CSV file into inventory_def.txt."""
    with open(file_path) as fh:
        csv_text = fh.read()
    data = call(ctx.obj.client.post, "/inventory-def/bulk",
                json_body={"csv_text": csv_text, "backup": not no_backup})
    success(data.get("message", "Import complete."))


@inventory_group.command("raw")
@click.pass_context
def raw(ctx):
    """Print the raw contents of inventory_def.txt."""
    data = call(ctx.obj.client.get, "/inventory-def/raw")
    click.echo(data.get("content", ""))


@inventory_group.command("ssh-test")
@click.option("--ip", required=True)
@click.option("--user", default="root")
@click.option("--port", type=int, default=22)
@click.option("--password", default=None)
@click.option("--key-path", default=None)
@click.pass_context
def ssh_test(ctx, ip, user, port, password, key_path):
    """Test SSH connectivity to a node from the backend host."""
    body = {"ip": ip, "user": user, "port": port, "password": password, "key_path": key_path}
    data = call(ctx.obj.client.post, "/inventory-def/ssh-test", json_body=body)
    render(data, ctx.obj.output)
    if not data.get("success"):
        raise SystemExit(1)
