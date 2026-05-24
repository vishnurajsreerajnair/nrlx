from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from nrlx import __version__
from nrlx.cache import get_cache_info, init_cache
from nrlx.exceptions import NRLXError

app = typer.Typer(
    name="nrlx",
    help="NRL eXtended: seismic instrument response tools.",
    no_args_is_help=True
)

console = Console()

@app.callback()
def main() -> None:
    """Run nrlx from the command line."""

@app.command()
def info(
    cache_root: Annotated[
        Path | None,
        typer.Option(
            "--cache-root",
            help="Custom cache root directory."
        ),
    ] = None,
) -> None:
    """Show nrlx version and cache information."""
    cache = get_cache_info(cache_root)

    table = Table(
        title="nrlx information", 
        show_header=True, 
        header_style="bold"
    )
    table.add_column("Field")
    table.add_column("Value")

    table.add_row(
        "Version", 
        __version__
    )
    table.add_row(
        "Cache root", 
        str(cache.root)
    )
    table.add_row(
        "NRL directory", 
        str(cache.nrl_dir)
    )
    table.add_row(
        "Index file", 
        str(cache.index_file)
    )
    table.add_row(
        "Cache exists", 
        str(cache.exists)
    )

    console.print(table)

@app.command("init-cache")
def init_cache_command(
    cache_root: Annotated[
        Path | None,
        typer.Option(
            "--cache-root",
            help="Custom cache root directory."
        ),
    ] = None,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help="Rewrite the cache index if it already exists."
        ),
    ] = False,
) -> None:
    """Initialize the local nrlx cache directory."""

    try:
        cache = init_cache(cache_root, force=force)
    except NRLXError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(
        Panel.fit(
            f"Cache initialized\n\n"
            f"Root: {cache.root}\n"
            f"NRL directory: {cache.nrl_dir}\n"
            f"Index: {cache.index_file}",
            title="nrlx",
            border_style="green",
        )
    )