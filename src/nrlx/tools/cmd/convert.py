"""The command converting response files between formats: nrlx convert"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from obspy import Inventory
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from nrlx.core.convert import output_format
from nrlx.io.inventory import (
    read_channels,
    split_channels,
    verify_written,
    writable_channels,
    write_inventory,
)
from nrlx.schema.response import ResponseFormat

console = Console()
errconsole = Console(stderr=True)


def convert(
    source: Annotated[
        str,
        typer.Argument(
            help="Response file obspy reads (StationXML, RESP, dataless SEED, "
            "XSEED, SC3ML); FILE#NET.STA.LOC.CHA for one channel."
        ),
    ],
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="File to write: .xml for StationXML, .resp for RESP, .pz for SACPZ.",
        ),
    ],
    response_format: Annotated[
        ResponseFormat | None,
        typer.Option("--format", help="Instead of the extension (.xml, .resp, .pz)."),
    ] = None,
    split: Annotated[
        bool,
        typer.Option("--split", help="One file per channel, named by its SEED id."),
    ] = False,
) -> None:
    """Convert a response file to StationXML, RESP or SACPZ.

    Every channel of the file is converted, or one with FILE#NET.STA.LOC.CHA; the
    channels the format cannot hold (no response, or not poles and zeros in m,
    m/s or m/s**2 for SACPZ) are skipped with a note. The file written is read
    back and compared with the input: StationXML and RESP must give the same
    curves, and for SACPZ, which keeps the first poles and zeros stage and the
    overall sensitivity, a note says how far it is from the whole response.

    Example:

    nrlx convert station.xml -o station.resp


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

    # the channels: FILE or FILE#NET.STA.LOC.CHA, split at the last #
    selected: str | None = None
    match source.rpartition("#"):
        case (name, "#", seed_id):
            source_file, selected = Path(name), seed_id
        case (_, _, name):
            source_file = Path(name)
    try:
        inventory = read_channels(source_file, selected)
    except (OSError, ValueError, LookupError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # the channels the format cannot hold are skipped, with a note; none held
    # is an error
    kept, skipped = writable_channels(inventory, fileformat)
    reasons = list(dict.fromkeys(reason for _, reason in skipped))
    grouped = [
        (
            reason,
            ", ".join(
                dict.fromkeys(seedid for seedid, why in skipped if why == reason)
            ),
        )
        for reason in reasons
    ]
    if not kept.networks:
        listed = "; ".join(f"{reason}: {seedids}" for reason, seedids in grouped)
        errconsole.print(
            f"[bold red]Error:[/bold red] Cannot write {fileformat}, {escape(listed)}."
        )
        raise typer.Exit(code=1)

    # one file, or one per channel named by its SEED id
    files: list[tuple[Path, Inventory]] = [(output, kept)]
    if split:
        files = [
            (output.with_name(f"{output.stem}_{seedid}{output.suffix}"), single)
            for seedid, single in split_channels(kept)
        ]

    # each file written, then read back
    notes: list[str] = list()
    try:
        for path, content in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_inventory(content, path, fileformat)
            notes += verify_written(content, path, fileformat)
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    for reason, seedids in grouped:
        console.print(
            f"note: skipped ({escape(reason)}): {escape(seedids)}", soft_wrap=True
        )
    for note in notes:
        console.print(f"note: {escape(note)}", soft_wrap=True)
    written = "\n".join(f"  {escape(str(path))}" for path, _ in files)
    console.print(
        Panel.fit(
            f"Converted to {fileformat}, read back and checked\n\n{written}",
            title="nrlx",
            border_style="green",
        )
    )
