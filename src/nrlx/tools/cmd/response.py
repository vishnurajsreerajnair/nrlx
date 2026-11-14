"""The command finding and writing responses: nrlx response"""

from __future__ import annotations

import shlex
from datetime import datetime
from pathlib import Path
from typing import Annotated

import httpx
import typer
from obspy import Inventory
from obspy.core.inventory.response import Response
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from nrlx.core.matching import varying_values
from nrlx.core.seed import band_codes
from nrlx.io.inventory import read_part
from nrlx.io.resp import write_resp
from nrlx.io.service import DEFAULT_BASE_URL
from nrlx.models.catalog import Found
from nrlx.models.nrlx import Nrlx
from nrlx.schema.prefixes import PrefixInput
from nrlx.schema.response import ResponseInput, Source

console = Console()
errconsole = Console(stderr=True)

# rows listed one by one; above, the rows are grouped by model
MAX_ROWS_LISTED = 20

# the times accepted by the options, UTC
TIME_FORMATS = ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]

# the parts of a response, in the order of the signal
PARTS = ["sensor", "datalogger", "integrated", "soh"]

# the combinations of parts offered by the interactive mode
COMBINATIONS = [
    ["sensor", "datalogger"],
    ["sensor"],
    ["datalogger"],
    ["integrated"],
    ["soh"],
]


def response(
    keys: Annotated[
        list[str] | None,
        typer.Argument(
            help="Keys to explore without a part, in every element (or --element)."
        ),
    ] = None,
    sensor: Annotated[
        list[str] | None,
        typer.Option(
            "--sensor",
            help="Keys of the sensor, comma-separated or repeated: words "
            "(luni, LP1) or conditions (LP=1, 'corner>=60', FR=100..500).",
        ),
    ] = None,
    datalogger: Annotated[
        list[str] | None,
        typer.Option("--datalogger", help="Keys of the datalogger."),
    ] = None,
    sensor_file: Annotated[
        str | None,
        typer.Option(
            "--sensor-file",
            help="Response of the sensor from a file obspy reads, in place of "
            "--sensor: FILE, or FILE#NET.STA.LOC.CHA for one of its channels.",
        ),
    ] = None,
    datalogger_file: Annotated[
        str | None,
        typer.Option(
            "--datalogger-file", help="Same as --sensor-file, for the datalogger."
        ),
    ] = None,
    integrated: Annotated[
        list[str] | None,
        typer.Option("--integrated", help="Keys of an integrated instrument (alone)."),
    ] = None,
    soh: Annotated[
        list[str] | None,
        typer.Option("--soh", help="Keys of a state of health channel (alone)."),
    ] = None,
    element: Annotated[
        str | None,
        typer.Option("--element", help="Element of the bare keys, e.g. sensor."),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the response: .xml for StationXML, .resp for RESP.",
        ),
    ] = None,
    response_format: Annotated[
        str | None,
        typer.Option("--format", help="stationxml or resp, instead of the extension."),
    ] = None,
    split: Annotated[
        bool,
        typer.Option("--split", help="One file per channel, named by its SEED id."),
    ] = False,
    network: Annotated[str | None, typer.Option("--network")] = None,
    station: Annotated[str | None, typer.Option("--station")] = None,
    location: Annotated[str | None, typer.Option("--location")] = None,
    channels: Annotated[
        list[str] | None,
        typer.Option(
            "--channels",
            help="Channel codes, comma-separated or repeated, written as given.",
        ),
    ] = None,
    starttime: Annotated[
        datetime | None,
        typer.Option("--starttime", formats=TIME_FORMATS, help="UTC."),
    ] = None,
    endtime: Annotated[
        datetime | None,
        typer.Option("--endtime", formats=TIME_FORMATS, help="UTC."),
    ] = None,
    latitude: Annotated[
        float | None, typer.Option("--latitude", help="Degrees.")
    ] = None,
    longitude: Annotated[
        float | None, typer.Option("--longitude", help="Degrees.")
    ] = None,
    elevation: Annotated[
        float, typer.Option("--elevation", help="Metres, with the coordinates.")
    ] = 0.0,
    depth: Annotated[
        float,
        typer.Option("--depth", help="Metres below the surface, with the coordinates."),
    ] = 0.0,
    interactive: Annotated[
        bool,
        typer.Option(
            "--interactive", "-i", help="Choose the parts and labels step by step."
        ),
    ] = False,
    source: Annotated[
        Source,
        typer.Option(
            "--source",
            help="Where the NRL parts come from: service, or local (nrlx local sync).",
        ),
    ] = "service",
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="NRL web service base URL."),
    ] = DEFAULT_BASE_URL,
) -> None:
    """Find the configurations of the NRL, and write their response.

    Without -o it only shows what each part matches: the catalog without any
    keys, the configurations of bare keys, and for each part (--sensor,
    --datalogger, --integrated, --soh) its matches and the parameters that still
    vary. Add keys until each part matches one configuration, then add -o FILE
    to write it. -i asks the parts and labels step by step and prints the same
    command line. The sensor or the datalogger can come from a file instead
    (--sensor-file, --datalogger-file), combined by nrlx with the other part.

    Example:

    nrlx response --sensor luni,tellus,LP=1
    --datalogger centaur,FR=100,FV=40Vpp,DF=Off,FP=Linear
    --network XY --station TST --location 00 --channels HHZ,HHN,HHE -o st.xml


    """
    try:
        nrl = Nrlx.from_cache(cache_root, base_url=base_url)
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # -i asks the NRL parts only
    if interactive and (sensor_file is not None or datalogger_file is not None):
        errconsole.print(
            "[bold red]Error:[/bold red] -i asks the NRL parts: give the files "
            "without -i."
        )
        raise typer.Exit(code=1)

    # the parts from files, read before anything else
    try:
        sensor_response = read_file_option(sensor_file)
        datalogger_response = read_file_option(datalogger_file)
    except (OSError, ValueError, LookupError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err
    from_files = [
        (part, value, partresponse)
        for part, value, partresponse in [
            ("sensor", sensor_file, sensor_response),
            ("datalogger", datalogger_file, datalogger_response),
        ]
        if value is not None and partresponse is not None
    ]
    files = [(part, value) for part, value, _ in from_files]

    # the interactive mode asks what the options give
    selections = [
        ("sensor", split_keys(sensor)),
        ("datalogger", split_keys(datalogger)),
        ("integrated", split_keys(integrated)),
        ("soh", split_keys(soh)),
    ]
    codes = split_keys(channels) or []
    if interactive:
        selections, network, station, location, codes, output = ask(nrl)
        line = command_line(
            selections, files, source, network, station, location, codes, output
        )
        console.print(
            f"\nThe same from the command line:\n{escape(line)}\n", soft_wrap=True
        )
    given = [(part, partkeys) for part, partkeys in selections if partkeys is not None]

    # bare keys explore; the parts are what -o writes
    if keys and (given or files):
        errconsole.print(
            "[bold red]Error:[/bold red] Keys without a part only explore: put them "
            "in --sensor, --datalogger, --integrated or --soh."
        )
        raise typer.Exit(code=1)
    if output is not None and not (given or files):
        errconsole.print(
            "[bold red]Error:[/bold red] Writing needs a part: --sensor, "
            "--datalogger, --integrated, --soh, or a file with --sensor-file or "
            "--datalogger-file."
        )
        raise typer.Exit(code=1)

    # the rules of the parts, the labels and the place, before any table
    if given or files:
        parts = {part: partkeys for part, partkeys in given}
        try:
            ResponseInput(
                sensor=parts.get("sensor"),
                datalogger=parts.get("datalogger"),
                sensor_response=sensor_response,
                datalogger_response=datalogger_response,
                integrated=parts.get("integrated"),
                soh=parts.get("soh"),
                network=network,
                station=station,
                location=location,
                channels=codes,
                starttime=starttime,
                endtime=endtime,
                latitude=latitude,
                longitude=longitude,
                elevation=elevation,
                depth=depth,
                source=source,
            )
        except ValueError as err:
            errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
            raise typer.Exit(code=1) from err

    # the catalog, or what the bare keys match
    if not given and not files and not keys:
        show_tree(nrl)
    elif not given and not files:
        try:
            found = nrl.find(split_keys(keys) or [], element)
        except ValueError as err:
            errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
            raise typer.Exit(code=1) from err
        show_found("keys", found, nrl.prefixes)
        if not found.rows:
            raise typer.Exit(code=1)
    else:
        # the parts from files, then what each part by keys matches
        for part, value, partresponse in from_files:
            stages = partresponse.response_stages
            summary = (
                f"stages: {len(stages)}, {stages[0].input_units} to "
                f"{stages[-1].output_units}"
                if stages
                else "no stages"
            )
            console.print(f"{part}: {escape(value)}, {escape(summary)}", soft_wrap=True)
        unique: list[tuple[str, str]] = list()
        for part, partkeys in given:
            try:
                found = nrl.find(partkeys, part)
            except ValueError as err:
                errconsole.print(
                    f"[bold red]Error:[/bold red] {part}: {escape(str(err))}"
                )
                raise typer.Exit(code=1) from err
            show_found(part, found, nrl.prefixes)
            match found.rows:
                case [(*_, configuration)]:
                    unique.append((part, configuration.instconfig))
                case []:
                    raise typer.Exit(code=1)
                case _:
                    pass

        # every part one configuration: the line to write it, or the file
        if len(unique) < len(given):
            if output is not None:
                errconsole.print(
                    "[bold red]Error:[/bold red] Each part must match one "
                    "configuration before writing: add keys from the tables."
                )
                raise typer.Exit(code=1)
        elif output is None:
            exact: list[tuple[str, list[str] | None]] = [
                (part, [instconfig]) for part, instconfig in unique
            ]
            line = command_line(
                exact, files, source, network, station, location, codes, None
            )
            console.print(
                f"\nEvery part matches one configuration. Add -o FILE to write:\n"
                f"{escape(line)} -o FILE",
                soft_wrap=True,
            )
        else:
            write(
                nrl,
                given,
                sensor_response,
                datalogger_response,
                source,
                network,
                station,
                location,
                codes,
                starttime,
                endtime,
                latitude,
                longitude,
                elevation,
                depth,
                output,
                response_format,
                split,
            )


def write(
    nrl: Nrlx,
    given: list[tuple[str, list[str]]],
    sensor_response: Response | None,
    datalogger_response: Response | None,
    source: Source,
    network: str | None,
    station: str | None,
    location: str | None,
    codes: list[str],
    starttime: datetime | None,
    endtime: datetime | None,
    latitude: float | None,
    longitude: float | None,
    elevation: float,
    depth: float,
    output: Path,
    response_format: str | None,
    split: bool,
) -> None:
    """Build the response and write its file or files

    Args:
        nrl: catalog, code table and service.
        given: each part and its keys.
        sensor_response: response of the sensor from a file, None for its keys.
        datalogger_response: response of the datalogger from a file, None for its
            keys.
        source: where the NRL parts come from, service or local.
        network: network code, None for the placeholder.
        station: station code, None for the placeholder.
        location: location code, None for the placeholder.
        codes: channel codes, empty for the placeholder.
        starttime: start of the validity, None for the placeholder.
        endtime: end of the validity, None for no end.
        latitude: latitude in degrees, None for the placeholder.
        longitude: longitude in degrees.
        elevation: elevation in metres.
        depth: depth below the surface in metres.
        output: file to write, the name of each file with --split.
        response_format: stationxml or resp, None for the extension of the file.
        split: whether to write one file per channel.


    """
    # the format, from the option or the extension
    match (response_format, output.suffix.lower()):
        case ("stationxml", _) | (None, ".xml"):
            fileformat = "stationxml"
        case ("resp", _) | (None, ".resp"):
            fileformat = "resp"
        case (None, suffix):
            errconsole.print(
                f"[bold red]Error:[/bold red] Cannot tell the format from "
                f"{escape(suffix or 'no extension')}: use .xml or .resp, or --format."
            )
            raise typer.Exit(code=1)
        case (other, _):
            errconsole.print(
                f"[bold red]Error:[/bold red] Unknown format {escape(other)}: "
                "stationxml or resp."
            )
            raise typer.Exit(code=1)

    parts = {part: partkeys for part, partkeys in given}
    try:
        inventory, combined = nrl.response(
            sensor=parts.get("sensor"),
            datalogger=parts.get("datalogger"),
            sensor_response=sensor_response,
            datalogger_response=datalogger_response,
            source=source,
            integrated=parts.get("integrated"),
            soh=parts.get("soh"),
            network=network,
            station=station,
            location=location,
            channels=codes or None,
            starttime=starttime,
            endtime=endtime,
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            depth=depth,
        )
    except httpx.HTTPError as err:
        errconsole.print(
            f"[bold red]Error:[/bold red] NRL service request failed "
            f"({escape(nrl.base_url)}). {escape(str(err))}"
        )
        raise typer.Exit(code=1) from err
    except (LookupError, ValueError, OSError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # one file, or one per channel named by its SEED id
    if split:
        files = [
            (
                output.with_name(f"{output.stem}_{seedid}{output.suffix}"),
                single,
            )
            for seedid, single in split_channels(inventory)
        ]
    else:
        files = [(output, inventory)]
    try:
        for path, content in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            match fileformat:
                case "stationxml":
                    content.write(str(path), format="STATIONXML")
                case _:
                    path.write_text(write_resp(content))
    except OSError as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # what the combination filled or corrected, and the channel codes the SEED norm
    # would name otherwise, as notes
    notes = [f"note: {note}" for note in combined] + [
        f"note: {channel.code} at {channel.sample_rate:g} sps, the SEED norm "
        f"gives the band {' or '.join(band_codes(channel.sample_rate))}"
        for channel in inventory[0][0]
        if codes
        and channel.sample_rate
        and band_codes(channel.sample_rate)
        and channel.code[:1] not in band_codes(channel.sample_rate)
    ]
    for note in notes:
        console.print(escape(note))

    written = "\n".join(f"  {escape(str(path))}" for path, _ in files)
    console.print(
        Panel.fit(
            f"Response written ({fileformat})\n\n{written}",
            title="nrlx",
            border_style="green",
        )
    )


def split_channels(inventory: Inventory) -> list[tuple[str, Inventory]]:
    """Each channel of an inventory in an inventory of its own, with its SEED id

    Args:
        inventory: inventory of a response, a station.

    Returns:
        the SEED id NET.STA.LOC.CHA and the inventory of each channel.


    """
    singles = list()
    for network in inventory:
        for station in network:
            for channel in station:
                # the inventory, with this network, station and channel only
                single = inventory.copy()
                single.networks = [network.copy()]
                single[0].stations = [station.copy()]
                single[0][0].channels = [channel.copy()]
                seedid = (
                    f"{network.code}.{station.code}."
                    f"{channel.location_code}.{channel.code}"
                )
                singles.append((seedid, single))

    return singles


def show_tree(nrl: Nrlx) -> None:
    """Print the catalog: each manufacturer with models, by element, with its counts

    Args:
        nrl: catalog.


    """
    table = Table(title="NRL catalog: add keys, or a part (--sensor ...)")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Models", justify="right")
    table.add_column("Configurations", justify="right")
    # the manufacturers that have models only, as the catalog lists some without
    manufacturers = [
        (element, manufacturer)
        for element, manufacturer in nrl.catalog.get_manufacturers()
        if manufacturer.models
    ]
    for element, manufacturer in manufacturers:
        configurations = sum(len(model.configurations) for model in manufacturer.models)
        table.add_row(
            element.name,
            manufacturer.name,
            str(len(manufacturer.models)),
            str(configurations),
        )
    console.print(table)


def show_found(part: str, found: Found, prefixes: list[PrefixInput]) -> None:
    """Print what keys match: the configuration, a few rows, or the models

    Args:
        part: part of the keys, or "keys" for bare keys.
        found: what the keys match.
        prefixes: code table, to name the parameters by their codes.


    """
    codes = {prefix.description: prefix.prefix for prefix in prefixes}
    rows = found.rows

    match rows:
        case []:
            console.print(f"[bold]{part}[/bold]: no match.")
            for hint in found.hints:
                console.print(f"  {escape(hint)}")
        case [(element, manufacturer, model, configuration)]:
            table = Table(title=f"{part}: {escape(configuration.instconfig)}")
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Element", element.name)
            table.add_row("Manufacturer", manufacturer.name)
            table.add_row("Model", model.name)
            table.add_row("Version", configuration.version)
            if configuration.description:
                table.add_row("Description", escape(configuration.description))
            for name, value in configuration.parameters.items():
                code = codes.get(name, "")
                table.add_row(escape(f"{name} {code}".strip()), escape(value))
            console.print(table)
        case _ if len(rows) <= MAX_ROWS_LISTED:
            table = Table(title=f"{part}: {len(rows)} configurations")
            table.add_column("Manufacturer")
            table.add_column("Model")
            table.add_column("Instconfig")
            for _, manufacturer, model, configuration in rows:
                table.add_row(
                    manufacturer.name, model.name, escape(configuration.instconfig)
                )
            console.print(table)
            console.print(
                f"Still varying: {escape(varying_line(found.varying, codes))}"
            )
        case _:
            # the rows of each model together, with what varies in them
            models: dict[tuple[str, str, str], list[dict[str, str]]] = dict()
            for element, manufacturer, model, configuration in rows:
                names = (element.name, manufacturer.name, model.name)
                models.setdefault(names, []).append(configuration.parameters)
            table = Table(
                title=f"{part}: {len(rows)} configurations in {len(models)} models"
            )
            table.add_column("Element")
            table.add_column("Manufacturer")
            table.add_column("Model")
            table.add_column("Configs", justify="right")
            table.add_column("Still varying")
            for names, parameters in models.items():
                elementname, manufacturername, modelname = names
                table.add_row(
                    elementname,
                    manufacturername,
                    modelname,
                    str(len(parameters)),
                    escape(varying_line(varying_values(parameters), codes)),
                )
            console.print(table)

    for note in found.notes:
        console.print(f"  {escape(note)}")


def varying_line(varying: dict[str, list[str]], codes: dict[str, str]) -> str:
    """The parameters that still vary, by code when they have one

    Args:
        varying: values of each varying parameter, by name.
        codes: code of each parameter name that has one.

    Returns:
        for example "LP 1 s/10 s · SG 400 V/m/s/1500 V/m/s", or "nothing".


    """
    line = (
        " · ".join(
            f"{codes.get(name, name)} {', '.join(values)}"
            for name, values in varying.items()
        )
        or "nothing"
    )

    return line


def read_file_option(value: str | None) -> Response | None:
    """Response of a part from the value of its file option

    Args:
        value: FILE, or FILE#NET.STA.LOC.CHA for one of its channels (split at the
            last #); None without the option.

    Returns:
        the response, None without the option.

    Raises:
        OSError: if the file cannot be read.
        ValueError: if obspy cannot read it, or the channel has no response.
        LookupError: if no channel or several match.


    """
    match value.rpartition("#") if value is not None else None:
        case None:
            response = None
        case (path, "#", seed_id):
            response = read_part(Path(path), seed_id)
        case (_, _, path):
            response = read_part(Path(path))

    return response


def split_keys(values: list[str] | None) -> list[str] | None:
    """Keys of a repeated option, each split on its commas

    Args:
        values: values of the option, None when not given.

    Returns:
        the keys, None when the option is not given.


    """
    keys = None
    if values is not None:
        keys = [key for value in values for key in value.split(",") if key]

    return keys


def command_line(
    selections: list[tuple[str, list[str] | None]],
    files: list[tuple[str, str]],
    source: Source,
    network: str | None,
    station: str | None,
    location: str | None,
    codes: list[str],
    output: Path | None,
) -> str:
    """The nrlx response command line of the parts and labels

    Args:
        selections: each part and its keys, None when not given.
        files: each part from a file and its option value, FILE or
            FILE#NET.STA.LOC.CHA.
        source: where the NRL parts come from, written only when local.
        network: network code, None when not given.
        station: station code, None when not given.
        location: location code, None when not given.
        codes: channel codes.
        output: file to write, None without.

    Returns:
        the command line, quoted for the shell.


    """
    words = ["nrlx", "response"]
    words += [
        word
        for part, partkeys in selections
        if partkeys is not None
        for word in [f"--{part}", ",".join(partkeys)]
    ]
    words += [word for part, value in files for word in [f"--{part}-file", value]]
    words += ["--source", source] if source != "service" else []
    words += [
        word
        for option, value in [
            ("--network", network),
            ("--station", station),
            ("--location", location),
            ("--channels", ",".join(codes) or None),
            ("-o", str(output) if output is not None else None),
        ]
        if value is not None
        for word in [option, value]
    ]
    line = shlex.join(words)

    return line


def ask(
    nrl: Nrlx,
) -> tuple[
    list[tuple[str, list[str] | None]],
    str | None,
    str | None,
    str | None,
    list[str],
    Path,
]:
    """Ask the parts, the labels and the file, step by step

    Args:
        nrl: catalog and code table.

    Returns:
        each part and its keys, the network, station and location codes, the
        channel codes and the file to write.


    """
    # the parts
    console.print("Which parts?")
    for number, combination in enumerate(COMBINATIONS, start=1):
        console.print(f"  {number}. {' + '.join(combination)}")
    choice = IntPrompt.ask(
        f"Choice (1-{len(COMBINATIONS)})",
        choices=[str(n) for n in range(1, len(COMBINATIONS) + 1)],
        show_choices=False,
    )
    combination = COMBINATIONS[choice - 1]
    chosen = {part: ask_part(nrl, part) for part in combination}
    selections = [(part, chosen.get(part)) for part in PARTS]

    # the labels and the file
    network = Prompt.ask("Network code", default="XX")
    station = Prompt.ask("Station code", default="STA")
    location = Prompt.ask("Location code", default="00")
    channels = Prompt.ask(
        "Channel codes, comma-separated (empty for one service placeholder)",
        default="",
        show_default=False,
    )
    codes = split_keys([channels]) or []
    output = Path(Prompt.ask("File to write (.xml or .resp)", default="response.xml"))

    return selections, network, station, location, codes, output


def ask_part(nrl: Nrlx, part: str) -> list[str]:
    """Ask a configuration of a part: its manufacturer, model, then each parameter

    Args:
        nrl: catalog and code table.
        part: element of the part, for example sensor.

    Returns:
        the instconfig of the configuration chosen, as the only key.


    """
    questions = {prefix.description: prefix.question for prefix in nrl.prefixes}
    rows = nrl.catalog.get_configurations(part)

    # the manufacturer, then the model
    manufacturers = sorted({manufacturer.name for _, manufacturer, _, _ in rows})
    manufacturer = choose(f"{part}: manufacturer", manufacturers)
    rows = [row for row in rows if row[1].name == manufacturer]
    models = sorted({model.name for _, _, model, _ in rows})
    model = choose(f"{part}: model", models)
    rows = [row for row in rows if row[2].name == model]

    # each parameter that still varies, until one configuration is left
    varying = varying_values([configuration.parameters for *_, configuration in rows])
    while len(rows) > 1 and varying:
        name, values = next(iter(varying.items()))
        value = choose(questions.get(name) or name, values)
        rows = [row for row in rows if row[3].parameters.get(name) == value]
        varying = varying_values(
            [configuration.parameters for *_, configuration in rows]
        )

    # configurations that differ by their instconfig only
    instconfigs = [configuration.instconfig for *_, configuration in rows]
    if len(instconfigs) > 1:
        instconfigs = [choose(f"{part}: configuration", instconfigs)]

    return instconfigs


def choose(question: str, options: list[str]) -> str:
    """Ask one of the options by its number, or take the only one

    Args:
        question: the question.
        options: the options.

    Returns:
        the option chosen.


    """
    console.print(f"\n{escape(question)}")
    match options:
        case [only]:
            console.print(f"  {escape(only)} (the only one)")
            chosen = only
        case _:
            for number, option in enumerate(options, start=1):
                console.print(f"  {number}. {escape(option)}")
            choice = IntPrompt.ask(
                f"Choice (1-{len(options)})",
                choices=[str(n) for n in range(1, len(options) + 1)],
                show_choices=False,
            )
            chosen = options[choice - 1]

    return chosen
