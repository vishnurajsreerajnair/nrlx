"""Command checking the response files: nrlx doctor"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
import typer
from obspy.core.inventory import Channel
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from nrlx.core.assets import PROVENANCE_SUBJECT
from nrlx.core.convert import check_frequencies
from nrlx.core.doctor import (
    Severity,
    check_amplitude,
    check_chains,
    check_codes,
    check_nominal_curve,
    check_nominal_kind,
    check_poles,
    check_sacpz,
    stage_changes,
)
from nrlx.io.inventory import evalresp_values, read_channels
from nrlx.io.sacpz import read_sacpz
from nrlx.io.service import DEFAULT_BASE_URL
from nrlx.models.nrlx import Nrlx
from nrlx.schema.response import Source

console = Console()
errconsole = Console(stderr=True)

# the groups of checks, the columns of the table
GROUPS = ["amplitude", "chains", "poles", "codes", "nominal"]


def doctor(
    file: Annotated[
        str,
        typer.Argument(
            help="Response file: StationXML, RESP, dataless SEED, XSEED, SC3ML or "
            "SACPZ (.pz); FILE#NET.STA.LOC.CHA for one channel."
        ),
    ],
    sensor: Annotated[
        list[str] | None,
        typer.Option(
            "--sensor",
            help="Keys of the sensor of the nominal, comma-separated or repeated, "
            "instead of the provenance comment.",
        ),
    ] = None,
    datalogger: Annotated[
        list[str] | None,
        typer.Option("--datalogger", help="Keys of the datalogger of the nominal."),
    ] = None,
    integrated: Annotated[
        list[str] | None,
        typer.Option("--integrated", help="Keys of an integrated instrument."),
    ] = None,
    source: Annotated[
        Source | None,
        typer.Option(
            "--source",
            help="Where the nominal comes from: service or local; default the "
            "comment's, else service.",
        ),
    ] = None,
    no_nominal: Annotated[
        bool,
        typer.Option("--no-nominal", help="Skip the comparison with the nominal."),
    ] = False,
    every: Annotated[
        bool,
        typer.Option("--all", help="List every check, the passed ones too."),
    ] = False,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="NRL web service base URL."),
    ] = DEFAULT_BASE_URL,
) -> None:
    """Check the responses of a file, channel by channel.

    Tier 2 checks each channel: its amplitude (the stated sensitivity against its
    stages, the normalization factors, the flat band, the FIRs), its chains of
    units and rates, its poles and zeros, and its SEED codes. Tier 3 compares it
    with the NRL nominal of the parts it is built from: those of the provenance
    comment nrlx writes, or --sensor/--datalogger/--integrated. An error exits
    with 1.

    Example:

    nrlx doctor station.xml

    nrlx doctor station.resp --sensor STS-2,SG=1500 --datalogger Q330,FR=100


    """
    # FILE or FILE#NET.STA.LOC.CHA, split at the last #
    selected: str | None = None
    match file.rpartition("#"):
        case (name, "#", seed_id):
            path, selected = Path(name), seed_id
        case (_, _, name):
            path = Path(name)
    # the keys of the nominal, comma-separated or repeated
    sensor_keys = [key for value in sensor or [] for key in value.split(",") if key]
    datalogger_keys = [
        key for value in datalogger or [] for key in value.split(",") if key
    ]
    integrated_keys = [
        key for value in integrated or [] for key in value.split(",") if key
    ]
    given = bool(sensor_keys or datalogger_keys or integrated_keys)

    # the findings of each channel by group, and the nominals built, once each
    rows: list[tuple[str, list[tuple[str, list[tuple[Severity, str]]]]]] = list()
    built: list[str] = list()
    if path.suffix.lower() in (".pz", ".sacpz"):
        # SACPZ: obspy does not read it, nrlx does; no stages
        try:
            blocks = read_sacpz(path.read_text())
        except (OSError, ValueError) as err:
            errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
            raise typer.Exit(code=1) from err
        kept = [block for block in blocks if selected in (None, block[0])]
        if not kept:
            listed = ", ".join(seedid for seedid, *_ in blocks) or "none"
            errconsole.print(
                f"[bold red]Error:[/bold red] No channel {escape(str(selected))} in "
                f"{escape(str(path))} (channels: {escape(listed)})."
            )
            raise typer.Exit(code=1)
        for seedid, zeros, poles, constant, rate in kept:
            code = seedid.rpartition(".")[2]
            rows.append(
                (
                    seedid,
                    [
                        ("amplitude", [("info", "SACPZ: no stages")]),
                        ("chains", [("info", "SACPZ: no stages")]),
                        ("poles", check_sacpz(zeros, poles, constant)),
                        ("codes", check_codes(code, rate, None)),
                        ("nominal", [("info", "SACPZ: not compared")]),
                    ],
                )
            )
    else:
        try:
            inventory = read_channels(path, selected)
        except (OSError, ValueError, LookupError) as err:
            errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
            raise typer.Exit(code=1) from err

        # the NRL, only to build a nominal
        nrl: Nrlx | None = None
        unavailable = ""
        if not no_nominal:
            try:
                nrl = Nrlx.from_cache(cache_root, base_url=base_url)
            except (OSError, ValueError) as err:
                unavailable = str(err)
        if given and nrl is None and not no_nominal:
            errconsole.print(f"[bold red]Error:[/bold red] {escape(unavailable)}")
            raise typer.Exit(code=1)

        # the nominal of each provenance comment (or of the keys), built once
        nominals: dict[str, tuple[Channel | None, str]] = dict()
        for net in inventory:
            for sta in net:
                for cha in sta:
                    seedid = f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}"
                    response = cha.response
                    rate = cha.sample_rate or None
                    if response is None:
                        missing: list[tuple[Severity, str]] = [("error", "no response")]
                        rows.append((seedid, [("amplitude", missing)]))
                        continue
                    units = (
                        response.instrument_sensitivity.input_units
                        if response.instrument_sensitivity is not None
                        else None
                    )
                    groups = [
                        ("amplitude", check_amplitude(response, rate)),
                        ("chains", check_chains(response, rate)),
                        ("poles", check_poles(response)),
                        ("codes", check_codes(cha.code, rate, units)),
                    ]

                    # tier 3: the nominal of the same parts
                    comment = next(
                        (
                            comment.value
                            for comment in cha.comments
                            if comment.subject == PROVENANCE_SUBJECT
                        ),
                        "",
                    )
                    key = "given" if given else comment
                    compared: list[tuple[Severity, str]]
                    if no_nominal:
                        compared = [("info", "not compared (--no-nominal)")]
                    elif nrl is None:
                        compared = [("info", f"not compared: {unavailable}")]
                    else:
                        if key not in nominals:
                            try:
                                nominals[key] = nrl.nominal(
                                    cha,
                                    sensor=sensor_keys or None,
                                    datalogger=datalogger_keys or None,
                                    integrated=integrated_keys or None,
                                    source=source,
                                )
                            except httpx.HTTPError as err:
                                nominals[key] = (
                                    None,
                                    f"NRL service request failed: {err}",
                                )
                            except (LookupError, ValueError, OSError) as err:
                                nominals[key] = (None, str(err))
                        nominal, built_from = nominals[key]
                        if nominal is None or nominal.response is None:
                            compared = [("info", f"not compared: {built_from}")]
                        else:
                            if built_from not in built:
                                built.append(built_from)
                            frequencies = check_frequencies(rate)
                            compared = check_nominal_kind(
                                response,
                                nominal.response,
                                rate,
                                nominal.sample_rate or None,
                            ) + check_nominal_curve(
                                frequencies,
                                evalresp_values(response, frequencies),
                                evalresp_values(nominal.response, frequencies),
                            )
                            if any(severity != "ok" for severity, _ in compared):
                                changes = stage_changes(
                                    list(response.response_stages),
                                    list(nominal.response.response_stages),
                                )
                                compared += [
                                    ("info", f"differs: {change}") for change in changes
                                ]
                    groups.append(("nominal", compared))
                    rows.append((seedid, groups))

    # one row per channel: ok, or how many warnings and errors in each group
    counted = f"{len(rows)} channel" if len(rows) == 1 else f"{len(rows)} channels"
    table = Table(title=f"Doctor: {escape(str(path))} ({counted})")
    table.add_column("channel")
    for group in GROUPS:
        table.add_column(group)
    for seedid, groups in rows:
        found = dict(groups)
        cells = list()
        for group in GROUPS:
            severities = [severity for severity, _ in found.get(group, [])]
            errors, warnings = severities.count("error"), severities.count("warning")
            if errors:
                plural = "s" if errors > 1 else ""
                cells.append(f"[bold red]{errors} error{plural}[/bold red]")
            elif warnings:
                plural = "s" if warnings > 1 else ""
                cells.append(f"[yellow]{warnings} warning{plural}[/yellow]")
            elif "ok" in severities:
                cells.append("[green]ok[/green]")
            else:
                cells.append("[dim]-[/dim]")
        table.add_row(escape(seedid), *cells)
    console.print(table)

    # what each nominal was built from
    for built_from in built:
        console.print(f"nominal: {escape(built_from)}")

    # the warnings and errors, with the info of their group (the stages that
    # differ from the nominal), or every finding with --all
    for seedid, groups in rows:
        for group, findings in groups:
            troubled = any(severity in ("warning", "error") for severity, _ in findings)
            for severity, message in findings:
                if (
                    every
                    or severity in ("warning", "error")
                    or (troubled and severity == "info")
                ):
                    console.print(
                        f"{style(severity)} {escape(seedid)} {group}: {escape(message)}"
                    )

    # an error fails the check
    if any(
        severity == "error"
        for _, groups in rows
        for _, findings in groups
        for severity, _ in findings
    ):
        raise typer.Exit(code=1)


def style(severity: Severity) -> str:
    """Severity in its colour, for the lines of the findings

    Args:
        severity: severity of a finding.

    Returns:
        the severity with its Rich markup.


    """
    match severity:
        case "ok":
            styled = "[green]ok     [/green]"
        case "info":
            styled = "[cyan]info   [/cyan]"
        case "warning":
            styled = "[yellow]warning[/yellow]"
        case "error":
            styled = "[bold red]error  [/bold red]"

    return styled
