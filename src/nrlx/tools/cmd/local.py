"""Commands of the local copy of the NRL: nrlx local sync, status, remove"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from nrlx.io.local import get_tree_dir, remove_tree, tree_size
from nrlx.io.service import DEFAULT_BASE_URL
from nrlx.models.nrlx import Nrlx

console = Console()
errconsole = Console(stderr=True)

local_app = typer.Typer(
    name="local",
    help="The local copy of the NRL, for nrlx response --source local.",
    no_args_is_help=True,
)


@local_app.command("sync")
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
    """Download the whole NRL, with the catalog and the code table.

    About 300 MB to download and 2.8 GB on disk, in the layout of the zip of the
    service. The copy, the catalog and the code table are replaced together; a
    failure keeps the previous ones.


    """
    console.print("Downloading the whole NRL (about 300 MB), then unzipping...")
    try:
        nrl, notes = Nrlx.sync_local(cache_root, base_url=base_url)
    except httpx.HTTPError as err:
        errconsole.print(
            f"[bold red]Error:[/bold red] NRL service request failed "
            f"({escape(base_url)}). {escape(str(err))}"
        )
        raise typer.Exit(code=1) from err
    except (ValueError, OSError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    for note in notes:
        console.print(f"note: {escape(note)}")
    tree = get_tree_dir(cache_root)
    responses, size = tree_size(tree)
    console.print(
        Panel.fit(
            "Local NRL synced\n\n"
            f"Folder: {escape(str(tree))}\n"
            f"Response files: {responses}\n"
            f"Size: {size / 1e9:.2f} GB\n"
            f"Configurations: {len(nrl.catalog.get_configurations())}",
            title="nrlx",
            border_style="green",
        )
    )


@local_app.command("status")
def status(
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Show the folder, the files, the size and the date of the local copy."""
    tree = get_tree_dir(cache_root)
    if not tree.is_dir():
        console.print(
            f"No local NRL copy in {escape(str(tree))}: run 'nrlx local sync'."
        )
        raise typer.Exit()

    responses, size = tree_size(tree)
    synced = datetime.fromtimestamp(tree.stat().st_mtime, tz=UTC)
    console.print(
        Panel.fit(
            "Local NRL\n\n"
            f"Folder: {escape(str(tree))}\n"
            f"Response files: {responses}\n"
            f"Size: {size / 1e9:.2f} GB\n"
            f"Synced: {synced:%Y-%m-%d %H:%M} UTC",
            title="nrlx",
            border_style="green",
        )
    )


@local_app.command("remove")
def remove(
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Remove without asking."),
    ] = False,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Delete the local copy; the catalog and the code table stay."""
    tree = get_tree_dir(cache_root)
    if not tree.is_dir():
        console.print(f"No local NRL copy in {escape(str(tree))}.")
        raise typer.Exit()

    # a copy costs a 300 MB download to get back
    _, size = tree_size(tree)
    if not yes and not typer.confirm(
        f"Remove the local NRL copy ({size / 1e9:.1f} GB) in {tree}?"
    ):
        console.print("Kept.")
        raise typer.Exit()
    try:
        remove_tree(tree)
    except OSError as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    console.print(
        Panel.fit(
            f"Local NRL removed\n\n{escape(str(tree))}",
            title="nrlx",
            border_style="green",
        )
    )
