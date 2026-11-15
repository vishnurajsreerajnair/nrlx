"""Commands of the assets: nrlx assets add, list, get, deprecate, delete, export,
import


"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from nrlx.core.convert import output_format
from nrlx.io.assets import get_assets_file
from nrlx.io.cache import (
    get_catalog_file,
    get_prefixes_file,
    read_catalog,
    read_prefixes,
)
from nrlx.io.inventory import (
    read_channels,
    split_channels,
    verify_written,
    write_inventory,
)
from nrlx.models.assets import Assets
from nrlx.schema.response import ResponseFormat

console = Console()
errconsole = Console(stderr=True)

assets_app = typer.Typer(
    name="assets",
    help="The assets: StationXML files as built, by UID, versioned, in a database.",
    no_args_is_help=True,
)


@assets_app.command("add")
def add(
    source: Annotated[
        Path, typer.Argument(help="Response file obspy reads, stored as StationXML.")
    ],
    uid: Annotated[
        str | None,
        typer.Option("--uid", help="UID of the asset, instead of the station code."),
    ] = None,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Add a file as the next version of an asset.

    The UID is the station code of the file unless --uid gives one. The file is
    stored as StationXML, read back and checked; a response the UID already has
    is refused.

    Example:

    nrlx assets add t13.xml


    """
    assets = Assets(db=db if db is not None else get_assets_file(cache_root))
    try:
        inventory = read_channels(source)
        row = assets.add(inventory, uid)
    except (OSError, ValueError, LookupError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    console.print(
        Panel.fit(
            f"Added {escape(row.uid)} v{row.version}\n\n"
            f"  {len(row.channels)} channels, {escape(str(assets.db))}",
            title="nrlx",
            border_style="green",
        )
    )


@assets_app.command("list")
def list_assets(
    uid: Annotated[
        str | None, typer.Argument(help="UID of the asset, every asset without.")
    ] = None,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """List the versions of the assets, with what tells their variants apart."""
    assets = Assets(db=db if db is not None else get_assets_file(cache_root))
    try:
        rows = assets.list(uid)
    except (ValueError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    if not rows:
        console.print(f"No assets in {escape(str(assets.db))}.")
    else:
        table = Table(title=f"Assets: {escape(str(assets.db))}")
        for column in [
            "UID",
            "Version",
            "Added",
            "Status",
            "Rate",
            "Units",
            "Sensitivity",
            "Sensor",
            "Datalogger",
            "Channels",
        ]:
            table.add_column(column)
        for row in rows:
            table.add_row(
                escape(row.uid),
                f"v{row.version}",
                row.added[:10],
                f"deprecated {row.deprecated[:10]}" if row.deprecated else "in use",
                f"{row.sample_rate:g}" if row.sample_rate else "",
                escape(row.input_units),
                f"{row.sensitivity:.6g}" if row.sensitivity is not None else "",
                escape(row.sensor or ""),
                escape(row.datalogger or ""),
                str(len(row.channels)),
            )
        console.print(table)


@assets_app.command("get")
def get(
    uid: Annotated[str, typer.Argument(help="UID of the asset.")],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="File to write: .xml for StationXML, .resp for RESP, .pz for SACPZ.",
        ),
    ],
    keys: Annotated[
        list[str] | None,
        typer.Argument(
            help="Keys of the variant, as in nrlx response (FR=100, STS-2), and "
            "rate=, units=."
        ),
    ] = None,
    version: Annotated[
        int | None,
        typer.Option("--version", help="The version, deprecated or not."),
    ] = None,
    response_format: Annotated[
        ResponseFormat | None,
        typer.Option("--format", help="Instead of the extension (.xml, .resp, .pz)."),
    ] = None,
    split: Annotated[
        bool,
        typer.Option("--split", help="One file per channel, named by its SEED id."),
    ] = False,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Write a version of an asset: the latest in use, or the one keys pick.

    The file written is read back and checked, as by nrlx convert.

    Example:

    nrlx assets get T13 FR=100 -o t13.xml


    """
    # the format, from the option or the extension
    try:
        fileformat = (
            response_format
            if response_format is not None
            else output_format(output.suffix)
        )
    except ValueError as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # the catalog for the keys on the NRL parts, when synced
    try:
        catalog = read_catalog(get_catalog_file(cache_root))
        prefixes = read_prefixes(get_prefixes_file(cache_root))
    except FileNotFoundError:
        catalog, prefixes = None, []
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err
    assets = Assets(
        db=db if db is not None else get_assets_file(cache_root),
        catalog=catalog,
        prefixes=prefixes,
    )
    try:
        row = assets.select(uid, keys, version)
        inventory = assets.get(row.uid, version=row.version)
    except (ValueError, LookupError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # one file, or one per channel named by its SEED id, each read back
    files = [(output, inventory)]
    if split:
        files = [
            (output.with_name(f"{output.stem}_{seedid}{output.suffix}"), single)
            for seedid, single in split_channels(inventory)
        ]
    notes: list[str] = list()
    try:
        for path, content in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_inventory(content, path, fileformat)
            notes += verify_written(content, path, fileformat)
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    for note in notes:
        console.print(f"note: {escape(note)}", soft_wrap=True)
    written = "\n".join(f"  {escape(str(path))}" for path, _ in files)
    console.print(
        Panel.fit(
            f"{escape(row.uid)} v{row.version} written ({fileformat})\n\n{written}",
            title="nrlx",
            border_style="green",
        )
    )


@assets_app.command("deprecate")
def deprecate(
    uid: Annotated[str, typer.Argument(help="UID of the asset.")],
    version: Annotated[int, typer.Option("--version", help="The version.")],
    undo: Annotated[
        bool, typer.Option("--undo", help="Put the version back in use.")
    ] = False,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Deprecate a version, so that get no longer picks it without --version."""
    assets = Assets(db=db if db is not None else get_assets_file(cache_root))
    try:
        assets.deprecate(uid, version, undo)
    except (ValueError, LookupError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    state = "back in use" if undo else "deprecated"
    console.print(f"{escape(uid)} v{version} {state}.")


@assets_app.command("delete")
def delete(
    uid: Annotated[str, typer.Argument(help="UID of the asset.")],
    version: Annotated[
        int | None,
        typer.Option("--version", help="The version, every version without."),
    ] = None,
    yes: Annotated[
        bool, typer.Option("--yes", "-y", help="Delete without asking.")
    ] = False,
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Delete a version of an asset, or every version of it. Asks first."""
    assets = Assets(db=db if db is not None else get_assets_file(cache_root))
    which = f"v{version} of {uid}" if version is not None else f"every version of {uid}"
    if not yes and not typer.confirm(f"Delete {which}? This cannot be undone."):
        console.print("Nothing deleted.")
        raise typer.Exit(code=0)
    try:
        deleted = assets.delete(uid, version)
    except (ValueError, LookupError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    console.print(f"Deleted {deleted} version{'s' if deleted > 1 else ''} of {uid}.")


@assets_app.command("export")
def export(
    folder: Annotated[Path, typer.Argument(help="Folder to write, missing or empty.")],
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Write every version as UID/vN.xml with a manifest.json, to share.

    Another database takes it with nrlx assets import.


    """
    assets = Assets(db=db if db is not None else get_assets_file(cache_root))
    try:
        files = assets.export_to(folder)
    except (OSError, ValueError, LookupError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    console.print(
        Panel.fit(
            f"Exported {len(files) - 1} versions\n\n  {escape(str(folder))}",
            title="nrlx",
            border_style="green",
        )
    )


@assets_app.command("import")
def import_assets(
    source: Annotated[
        Path, typer.Argument(help="Folder of nrlx assets export, or a .sqlite.")
    ],
    db: Annotated[
        Path | None,
        typer.Option("--db", help="Database, instead of assets.sqlite in the cache."),
    ] = None,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Merge an export or another database: new versions added, the same skipped.

    A version that differs from the one here with the same UID and number stops
    the import before anything is written.


    """
    assets = Assets(db=db if db is not None else get_assets_file(cache_root))
    try:
        added, skipped = assets.import_from(source)
    except (OSError, ValueError, LookupError, sqlite3.Error) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    console.print(
        Panel.fit(
            f"Imported {added} versions, {skipped} already here\n\n"
            f"  {escape(str(assets.db))}",
            title="nrlx",
            border_style="green",
        )
    )
