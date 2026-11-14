"""Command building the responses: nrlx build"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from nrlx.io.service import DEFAULT_BASE_URL
from nrlx.models.build import Build
from nrlx.models.instrument import Instrument
from nrlx.models.nrlx import Nrlx
from nrlx.schema.response import ResponseFormat

console = Console()
errconsole = Console(stderr=True)


def split_values(values: list[str] | None) -> list[str]:
    """Values of a repeatable flag, each split at the commas

    --sensor-keys a,b,c and --sensor-key a --sensor-key b give the same list: click
    allows a variable number of values only on the arguments, not on the options.

    Args:
        values: values of the flag, None when not given.

    Returns:
        values split at the commas, without the empty ones.


    """
    parts = [part.strip() for value in values or [] for part in value.split(",")]
    split = [part for part in parts if part]

    return split


def build(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Destination file for the built response."),
    ],
    sensor_instconfig: Annotated[
        str | None,
        typer.Option(
            "--sensor-instconfig",
            help="Exact sensor instconfig string. Skips catalog resolution.",
        ),
    ] = None,
    sensor_manufacturer: Annotated[
        str | None,
        typer.Option("--sensor-manufacturer", help="Sensor manufacturer filter."),
    ] = None,
    sensor_model: Annotated[
        str | None,
        typer.Option("--sensor-model", help="Sensor model filter."),
    ] = None,
    sensor_keys: Annotated[
        list[str] | None,
        typer.Option(
            "--sensor-keys",
            "--sensor-key",
            help="Comma-separated keys matched anywhere in a sensor "
            "configuration (manufacturer, model, instconfig, parameter "
            "values), e.g. --sensor-keys streckeisen,STS-2,EG3. All keys "
            "must match; if the selection is ambiguous the candidates are "
            "listed - add distinguishing fragments from them. Quote keys "
            "containing spaces: --sensor-keys 'STS-2,100 Hz'. Repeatable.",
        ),
    ] = None,
    datalogger_instconfig: Annotated[
        str | None,
        typer.Option(
            "--datalogger-instconfig",
            help="Exact datalogger instconfig string. Skips catalog resolution.",
        ),
    ] = None,
    datalogger_manufacturer: Annotated[
        str | None,
        typer.Option(
            "--datalogger-manufacturer", help="Datalogger manufacturer filter."
        ),
    ] = None,
    datalogger_model: Annotated[
        str | None,
        typer.Option("--datalogger-model", help="Datalogger model filter."),
    ] = None,
    datalogger_keys: Annotated[
        list[str] | None,
        typer.Option(
            "--datalogger-keys",
            "--datalogger-key",
            help="Comma-separated keys matched anywhere in a datalogger "
            "configuration, e.g. --datalogger-keys Q330HR_PG1,FR40. "
            "Repeatable.",
        ),
    ] = None,
    response_format: Annotated[
        ResponseFormat,
        typer.Option("--format", help="Response output format."),
    ] = "stationxml",
    compress: Annotated[
        bool,
        typer.Option("--zip", help="Request a zipped response."),
    ] = False,
    network: Annotated[str | None, typer.Option("--network")] = None,
    station: Annotated[str | None, typer.Option("--station")] = None,
    location: Annotated[str | None, typer.Option("--location")] = None,
    channels: Annotated[
        list[str] | None,
        typer.Option(
            "--channels",
            "--channel",
            help="Comma-separated channel code labels, e.g. "
            "--channels EHZ,EHN,EHE. With several, one file is written per "
            "channel (or one merged file with --merge-channels). Repeatable.",
        ),
    ] = None,
    merge_channels: Annotated[
        bool,
        typer.Option(
            "--merge-channels",
            help="Merge multiple --channels responses into one StationXML file.",
        ),
    ] = False,
    starttime: Annotated[str | None, typer.Option("--starttime")] = None,
    endtime: Annotated[str | None, typer.Option("--endtime")] = None,
    latitude: Annotated[
        float | None,
        typer.Option(
            "--latitude",
            help="Latitude of the station in degrees, written on the station and "
            "its channels. Needs --longitude.",
        ),
    ] = None,
    longitude: Annotated[
        float | None,
        typer.Option(
            "--longitude",
            help="Longitude of the station in degrees. Needs --latitude.",
        ),
    ] = None,
    elevation: Annotated[
        float,
        typer.Option(
            "--elevation",
            help="Elevation of the station in metres, with the coordinates.",
        ),
    ] = 0.0,
    depth: Annotated[
        float,
        typer.Option(
            "--depth",
            help="Depth of the sensors below the surface in metres, with the "
            "coordinates.",
        ),
    ] = 0.0,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
    base_url: Annotated[
        str,
        typer.Option("--base-url", help="NRL web service base URL."),
    ] = DEFAULT_BASE_URL,
) -> None:
    """Build an instrument response from the NRL catalog and save it to a file.

    Select the sensor with --sensor-keys (or --sensor-manufacturer/--sensor-model,
    or an exact --sensor-instconfig); optionally cascade a datalogger the same
    way. One --channels value labels the single output; several write one file
    per channel, or one merged StationXML inventory with --merge-channels.
    --latitude and --longitude (with --elevation and --depth, 0 by default) place
    the station and its channels.

    Example:
    nrlx build --sensor-keys streckeisen,STS-2,EG3,SG1500
    --datalogger-keys Q330HR_PG1,FR40,ADHR,LRbelow100
    --network XY --station MYSTN --channels EHZ,EHN,EHE --merge-channels
    --latitude 49.096 --longitude 8.432 --elevation 112 -o station.xml


    """
    # the request, validated before reading the catalog
    try:
        sensor = Instrument(
            instconfig=sensor_instconfig,
            manufacturer=sensor_manufacturer,
            model=sensor_model,
            keys=split_values(sensor_keys),
        )

        # the datalogger only when selected, the sensor alone otherwise
        datalogger = None
        if (
            datalogger_instconfig is not None
            or datalogger_manufacturer is not None
            or datalogger_model is not None
            or datalogger_keys
        ):
            datalogger = Instrument(
                instconfig=datalogger_instconfig,
                manufacturer=datalogger_manufacturer,
                model=datalogger_model,
                keys=split_values(datalogger_keys),
            )

        request = Build(
            sensor=sensor,
            datalogger=datalogger,
            format=response_format,
            compress=compress,
            network=network,
            station=station,
            location=location,
            channels=split_values(channels),
            merge_channels=merge_channels,
            starttime=starttime,
            endtime=endtime,
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            depth=depth,
        )
    except ValueError as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # the responses, after resolving the selections in the catalog
    try:
        nrl = Nrlx.from_cache(cache_root, base_url=base_url)
        responses = request.build(nrl)
    except httpx.HTTPError as err:
        errconsole.print(
            f"[bold red]Error:[/bold red] NRL service request failed "
            f"({escape(base_url)}). {escape(str(err))}"
        )
        raise typer.Exit(code=1) from err
    except (LookupError, OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    # a single file, or a file for each channel with its code after the name
    try:
        match responses:
            case [(_, response)]:
                files = [response.save(output)]
            case _:
                files = [
                    response.save(output.with_stem(f"{output.stem}_{channel}"))
                    for channel, response in responses
                ]
    except OSError as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    _, firstresponse = responses[0]
    lines = "\n".join(f"File: {escape(str(path))}" for path in files)
    console.print(
        Panel.fit(
            f"Response built\n\n{lines}\n"
            f"Instconfig: {escape(firstresponse.instconfig)}\n"
            f"Format: {response_format}{'.zip' if compress else ''}",
            title="nrlx",
            border_style="green",
        )
    )
