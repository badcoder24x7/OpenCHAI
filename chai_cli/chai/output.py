"""
CHAI CLI — Output rendering + error handling
──────────────────────────────────────────────
No third-party formatting dependency (no `rich`) so the CLI's dependency
footprint stays minimal: just `click` + `requests`.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Optional

import click

from .client import ChaiAPIError, ChaiConnectionError, ChaiError


def print_json(data: Any) -> None:
    click.echo(json.dumps(data, indent=2, default=str))


def _fmt_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def print_table(rows: list, columns: Optional[list] = None) -> None:
    if not rows:
        click.echo("(no results)")
        return

    if columns is None:
        columns = []
        for r in rows:
            if not isinstance(r, dict):
                columns = None
                break
            for k in r.keys():
                if k not in columns:
                    columns.append(k)

    if not columns:
        for r in rows:
            click.echo(_fmt_cell(r))
        return

    widths = {
        c: max([len(c)] + [len(_fmt_cell(r.get(c))) for r in rows])
        for c in columns
    }
    header = "  ".join(c.upper().ljust(widths[c]) for c in columns)
    click.echo(header)
    click.echo("  ".join("-" * widths[c] for c in columns))
    for r in rows:
        click.echo("  ".join(_fmt_cell(r.get(c)).ljust(widths[c]) for c in columns))


def render(data: Any, output_format: str = "table", columns: Optional[list] = None) -> None:
    """Render an API response either as raw JSON or as a best-effort table."""
    if output_format == "json":
        print_json(data)
        return

    if data is None:
        click.echo("(no content)")
        return

    if isinstance(data, list):
        print_table(data, columns)
        return

    if isinstance(data, dict):
        # Common API shape: {"items": [...], "total": N, ...}. Tabulate the
        # list field and print any scalar metadata fields above it.
        list_field = None
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                list_field = k
                break

        if list_field is not None:
            meta = {k: v for k, v in data.items() if k != list_field}
            for k, v in meta.items():
                if not isinstance(v, (dict, list)):
                    click.echo(f"{k}: {v}")
            if meta:
                click.echo("")
            print_table(data[list_field], columns)
        else:
            print_table([data], columns)
        return

    click.echo(str(data))


def error(msg: str) -> None:
    click.secho(f"Error: {msg}", fg="red", err=True)


def success(msg: str) -> None:
    click.secho(msg, fg="green")


def warn(msg: str) -> None:
    click.secho(msg, fg="yellow", err=True)


def call(fn: Callable, *args: Any, **kwargs: Any) -> Any:
    """
    Invoke an API call, translating ChaiError subclasses into a clean
    stderr message + exit(1) instead of a Python traceback.

    Usage:  data = call(ctx.obj.client.get, "/nodes")
    """
    try:
        return fn(*args, **kwargs)
    except ChaiAPIError as exc:
        detail = exc.detail
        if isinstance(detail, list):
            # FastAPI 422 validation error format
            click.secho(f"Error: {exc.method} {exc.path} -> HTTP {exc.status_code}", fg="red", err=True)
            for item in detail:
                if isinstance(item, dict):
                    loc = ".".join(str(p) for p in item.get("loc", []) if p != "body")
                    click.secho(f"  {loc}: {item.get('msg')}", fg="red", err=True)
                else:
                    click.secho(f"  {item}", fg="red", err=True)
        else:
            click.secho(f"Error: {detail}", fg="red", err=True)
        if exc.status_code == 401:
            warn("Hint: run `chai auth login` to authenticate.")
        elif exc.status_code == 403:
            warn("Hint: this action requires admin role / group membership on the backend host.")
        sys.exit(1)
    except ChaiConnectionError as exc:
        error(str(exc))
        warn("Hint: check --base-url / `chai config set --base-url`, and that the backend is running.")
        sys.exit(1)
    except ChaiError as exc:
        error(str(exc))
        sys.exit(1)
