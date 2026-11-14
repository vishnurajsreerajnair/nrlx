"""Commands of the NRL service and of the local cache: status, sync, prefixes"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

import nrlx
from nrlx.core.matching import contains
from nrlx.io.cache import (
    get_cache_root,
    get_catalog_file,
    get_prefixes_file,
    read_prefixes,
)
from nrlx.io.service import DEFAULT_BASE_URL, get
from nrlx.models.nrlx import Nrlx

console = Console()
errconsole = Console(stderr=True)


def status(
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="NRL web service base URL."),
    ] = DEFAULT_BASE_URL,
    live: Annotated[
        bool,
        typer.Option("--live", help="Also check whether the NRL service is reachable."),
    ] = False,
) -> None:
    """Show version, local cache info, and (with --live) service connectivity."""
    catalog_file = get_catalog_file(cache_root)

    table = Table(title="nrlx status", show_header=True, header_style="bold")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Version", nrlx.__version__)
    table.add_row("Cache root", escape(str(get_cache_root(cache_root))))
    table.add_row("NRL directory", escape(str(catalog_file.parent)))
    table.add_row("Catalog cached", str(catalog_file.exists()))

    # the version endpoint answers when the service is reachable
    if live:
        try:
            serviceversion = get(base_url, "version").decode().strip()
        except httpx.HTTPError as err:
            table.add_row("Service reachable", "[bold red]No[/bold red]")
            console.print(table)
            errconsole.print(
                f"[bold red]Error:[/bold red] NRL service request failed "
                f"({escape(base_url)}). {escape(str(err))}"
            )
            raise typer.Exit(code=1) from err
        table.add_row("Service reachable", "[bold green]Yes[/bold green]")
        table.add_row("Service version", escape(serviceversion))

    console.print(table)


def sync(
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="NRL web service base URL."),
    ] = DEFAULT_BASE_URL,
) -> None:
    """Download the current NRL catalog and code table into the local cache.

    Creates the cache directory first if it doesn't exist yet - safe to run
    on a fresh machine, and safe to re-run any time to refresh the catalog.
    The download is validated first: a broken one keeps the previous files.


    """
    try:
        nrl = Nrlx.sync(cache_root, base_url=base_url)
    except httpx.HTTPError as err:
        errconsole.print(
            f"[bold red]Error:[/bold red] NRL service request failed "
            f"({escape(base_url)}). {escape(str(err))}"
        )
        raise typer.Exit(code=1) from err
    except (ValueError, OSError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    configurations = nrl.catalog.get_configurations()
    console.print(
        Panel.fit(
            "Catalog synced\n\n"
            f"File: {escape(str(get_catalog_file(cache_root)))}\n"
            f"Configurations: {len(configurations)}\n"
            f"Codes: {len(nrl.prefixes)}",
            title="nrlx",
            border_style="green",
        )
    )


def prefixes(
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by prefix or meaning, e.g. LP or 'corner'."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Explain the two-letter parameter codes inside instconfig strings.

    instconfigs pack their parameters into coded fragments - LP120 means
    Long-Period Corner of 120 s, FR500 a Final Sample Rate of 500 Hz, FV10Vpp
    a Full-Scale Voltage of 10 Vpp. This reads the official code table that
    'nrlx sync' saves, so you can decode candidate lists and pick better keys.


    """
    try:
        rows = read_prefixes(get_prefixes_file(cache_root))
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    table = Table(title="NRL instconfig parameter prefixes")
    table.add_column("Prefix")
    table.add_column("Meaning")
    table.add_column("Question it answers")

    # the query filters by prefix or meaning
    for row in sorted(rows, key=lambda row: row.prefix):
        meaning = row.description.replace("_", " ")
        if contains(f"{row.prefix} {meaning}", query):
            table.add_row(row.prefix, meaning, row.question)

    console.print(table)
