from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="nrlx",
    help="NRL eXtended: build, validate, and inspect seismic instrument responses.",
)

console = Console()


@app.command()
def version() -> None:
    """Show installed nrlx version."""
    from nrlx import __version__

    console.print(f"nrlx {__version__}")


@app.command()
def doctor(path: str) -> None:
    """Placeholder response validator."""
    console.print(f"[yellow]Doctor not implemented yet.[/yellow] File: {path}")


def main() -> None:
    app()