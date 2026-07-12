from __future__ import annotations

from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from nrlx import __version__
from nrlx.cache import get_cache_info, get_catalog_file
from nrlx.cache import sync_catalog as _sync_catalog
from nrlx.catalog import Catalog
from nrlx.client import DEFAULT_NRL_BASE_URL, NRLClient
from nrlx.doctor import HealthReport, Severity, infer_format
from nrlx.exceptions import NrlxError
from nrlx.formats import ResponseFormat
from nrlx.inventory import merge_stationxml
from nrlx.nrl import BuiltResponse, Nrlx

app = typer.Typer(
    name="nrlx",
    help="NRL eXtended: seismic instrument response tools.",
    no_args_is_help=True,
    add_completion=False
)

console = Console()

CacheRootOption = Annotated[
    Path | None,
    typer.Option("--cache-root", help="Custom cache root directory."),
]
BaseUrlOption = Annotated[
    str,
    typer.Option("--base-url", help="NRL web service base URL."),
]
LimitOption = Annotated[
    int,
    typer.Option("--limit", min=1, max=1000, help="Maximum rows to display."),
]
ElementFilterOption = Annotated[
    str | None,
    typer.Option("--element", help="Filter by element group, for example sensor."),
]
ManufacturerFilterOption = Annotated[
    str | None,
    typer.Option("--manufacturer", help="Filter by manufacturer name."),
]
ModelFilterOption = Annotated[
    str | None,
    typer.Option("--model", help="Filter by model name."),
]

def _fail(exc: NrlxError, *, prefix: str = "Error") -> NoReturn:
    """Print a red error message and exit with status 1."""
    # escape(): exception text is data - square brackets in it (for example
    # "pip install 'nrlx[obspy]'") must not be eaten as Rich markup tags.
    console.print(f"[bold red]{prefix}:[/bold red] {escape(str(exc))}")
    raise typer.Exit(code=1) from exc

def _success(body: str) -> None:
    """Print a green success panel."""
    console.print(Panel.fit(body, title="nrlx", border_style="green"))

def _split_csv(values: list[str] | None) -> list[str] | None:
    """Expand comma-separated option values into a flat list.

    Lets one flag carry several values (--sensor-keys a,b,c) while the
    repeated form (--sensor-key a --sensor-key b) keeps working - Click only
    allows variable-length values on positional arguments, not options.


    """
    if values is None:
        return None
    split = [part.strip() for value in values for part in value.split(",")]
    return [part for part in split if part] or None

@app.callback()
def main() -> None:
    """Run nrlx from the command line."""

@app.command()
def status(
    cache_root: CacheRootOption = None,
    base_url: BaseUrlOption = DEFAULT_NRL_BASE_URL,
    live: Annotated[
        bool,
        typer.Option("--live", help="Also check whether the NRL service is reachable."),
    ] = False
) -> None:
    """Show version, local cache info, and (with --live) service connectivity."""
    cache = get_cache_info(cache_root)

    table = Table(
        title="nrlx status",
        show_header=True,
        header_style="bold"
    )
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Version", __version__)
    table.add_row("Cache root", str(cache.root))
    table.add_row("NRL directory", str(cache.nrl_dir))
    table.add_row("Catalog cached", str(get_catalog_file(cache_root).exists()))

    if not live:
        console.print(table)
        return

    client = NRLClient(base_url=base_url)
    try:
        client.ping()
    except NrlxError as exc:
        table.add_row("Service reachable", "[bold red]No[/bold red]")
        console.print(table)
        _fail(exc)

    table.add_row("Service reachable", "[bold green]Yes[/bold green]")
    console.print(table)

@app.command()
def sync(
    cache_root: CacheRootOption = None,
    base_url: BaseUrlOption = DEFAULT_NRL_BASE_URL,
) -> None:
    """Download the current NRL catalog into the local cache.

    Creates the cache directory first if it doesn't exist yet - safe to run
    on a fresh machine, and safe to re-run any time to refresh the catalog.


    """
    try:
        catalog_file = _sync_catalog(
            cache_root,
            base_url=base_url
        )
    except NrlxError as exc:
        _fail(exc)

    _success(f"Catalog synced\n\nFile: {catalog_file}")

@app.command()
def prefixes(
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by prefix or meaning, e.g. LP or 'corner'."),
    ] = None,
    base_url: BaseUrlOption = DEFAULT_NRL_BASE_URL,
) -> None:
    """Explain the two-letter parameter codes inside instconfig strings.

    instconfigs pack their parameters into coded fragments - LP120 means
    Long-Period Corner of 120 s, FR500 a Final Sample Rate of 500 Hz, FV10Vpp
    a Full-Scale Voltage of 10 Vpp. This fetches the official code table from
    the NRL service, so you can decode candidate lists and pick better keys.


    """
    client = NRLClient.for_base_url(base_url)

    try:
        rows = client.get(
            "prefix-lookup", params={"format": "json", "nodata": 404}
        ).json()
    except NrlxError as exc:
        _fail(exc)

    table = Table(title="NRL instconfig parameter prefixes")
    table.add_column("Prefix")
    table.add_column("Meaning")
    table.add_column("Question it answers")

    for row in sorted(rows, key=lambda r: str(r.get("prefix", ""))):
        if not isinstance(row, dict):
            continue
        prefix = str(row.get("prefix", ""))
        meaning = str(row.get("description", "")).replace("_", " ")
        question = str(row.get("question", ""))
        if query and query.lower() not in f"{prefix} {meaning}".lower():
            continue
        table.add_row(prefix, meaning, question)

    console.print(table)

browse_app = typer.Typer(help="Browse the locally cached NRL catalog.")
app.add_typer(browse_app, name="browse")

@browse_app.callback()
def browse_main(
    ctx: typer.Context,
    cache_root: CacheRootOption = None
) -> None:
    try:
        ctx.obj = Catalog.from_file(get_catalog_file(cache_root))
    except NrlxError as exc:
        _fail(exc)

@browse_app.command("summary")
def browse_summary(ctx: typer.Context) -> None:
    """Show catalog-wide counts."""
    catalog: Catalog = ctx.obj
    summary = catalog.summary

    table = Table(title="NRL catalog summary")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("File", str(summary.path))
    table.add_row("Format version", summary.format_version)
    table.add_row("Element groups", str(summary.element_count))
    table.add_row("Manufacturers", str(summary.manufacturer_count))
    table.add_row("Models", str(summary.model_count))
    table.add_row("Configurations", str(summary.configuration_count))
    console.print(table)

@browse_app.command("elements")
def browse_elements(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by element name, for example sensor."),
    ] = None
) -> None:
    """List top-level element groups, for example sensor and datalogger."""
    catalog: Catalog = ctx.obj

    table = Table(title="NRL catalog elements")
    table.add_column("Element")
    table.add_column("Manufacturers", justify="right")
    table.add_column("Models", justify="right")
    table.add_column("Configurations", justify="right")

    for row in catalog.elements(name=query):
        table.add_row(
            row.name,
            str(row.manufacturer_count),
            str(row.model_count),
            str(row.configuration_count)
        )

    console.print(table)

@browse_app.command("manufacturers")
def browse_manufacturers(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by manufacturer name."),
    ] = None,
    element: ElementFilterOption = None,
    limit: LimitOption = 50
) -> None:
    """List manufacturers."""
    catalog: Catalog = ctx.obj
    rows = catalog.manufacturers(element=element, name=query)[:limit]

    table = Table(title="NRL catalog manufacturers")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Models", justify="right")
    table.add_column("Configurations", justify="right")

    for row in rows:
        table.add_row(
            row.element,
            row.name,
            str(row.model_count),
            str(row.configuration_count)
        )

    console.print(table)

@browse_app.command("models")
def browse_models(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by model name."),
    ] = None,
    element: ElementFilterOption = None,
    manufacturer: ManufacturerFilterOption = None,
    limit: LimitOption = 50
) -> None:
    """List models."""
    catalog: Catalog = ctx.obj
    rows = catalog.models(
        element=element,
        manufacturer=manufacturer,
        name=query
    )[:limit]

    table = Table(title="NRL catalog models")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Model")
    table.add_column("Configurations", justify="right")

    for row in rows:
        table.add_row(
            row.element,
            row.manufacturer,
            row.name,
            str(row.configuration_count)
        )

    console.print(table)

@browse_app.command("configs")
def browse_configs(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(
            help="Free-text search across manufacturer, model, and instconfig."
        ),
    ] = None,
    element: ElementFilterOption = None,
    manufacturer: ManufacturerFilterOption = None,
    model: ModelFilterOption = None,
    instconfig: Annotated[
        str | None,
        typer.Option("--instconfig", help="Filter by instconfig substring."),
    ] = None,
    limit: LimitOption = 50
) -> None:
    """List response configurations.

    Pass a free-text QUERY to search manufacturer, model, and instconfig at
    once (e.g. 'nrlx browse configs lunitek'). Without QUERY, --element/
    --manufacturer/--model/--instconfig narrow the listing precisely instead.


    """
    catalog: Catalog = ctx.obj

    if query is not None:
        rows = catalog.search(query, element=element)[:limit]
    else:
        rows = catalog.configurations(
            element=element,
            manufacturer=manufacturer,
            model=model,
            instconfig=instconfig
        )[:limit]

    table = Table(title="NRL catalog configurations")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Model")
    table.add_column("Instconfig")
    table.add_column("Version")

    for row in rows:
        table.add_row(
            row.element, row.manufacturer, row.model, row.instconfig, row.version
        )

    console.print(table)

@app.command()
def build(
    output: Annotated[
        Path,
        typer.Option(
            "--output", "-o",
            help="Destination file for the built response."
        ),
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
    format: Annotated[
        ResponseFormat,
        typer.Option("--format", help="Response output format."),
    ] = ResponseFormat.STATIONXML,
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
            help="Merge multiple --channels responses into one StationXML "
            "file (needs the nrlx[obspy] extra).",
        ),
    ] = False,
    starttime: Annotated[str | None, typer.Option("--starttime")] = None,
    endtime: Annotated[str | None, typer.Option("--endtime")] = None,
    cache_root: CacheRootOption = None,
    base_url: BaseUrlOption = DEFAULT_NRL_BASE_URL,
) -> None:
    """Build an instrument response from the NRL catalog and save it to a file.

    Select the sensor with --sensor-keys (or --sensor-manufacturer/--sensor-model,
    or an exact --sensor-instconfig); optionally cascade a datalogger the same
    way. One --channels value labels the single output; several write one file
    per channel, or one merged StationXML inventory with --merge-channels.

    Example:
    nrlx build --sensor-keys streckeisen,STS-2,EG3,SG1500
    --datalogger-keys Q330HR_PG1,FR40,ADHR,LRbelow100
    --network XY --station MYSTN --channels EHZ,EHN,EHE --merge-channels -o station.xml


    """
    sensor_keys = _split_csv(sensor_keys)
    datalogger_keys = _split_csv(datalogger_keys)
    channels = _split_csv(channels)

    try:
        nrl = Nrlx.from_cache(cache_root, base_url=base_url)

        # Resolve human selections down to exact instconfig strings first, so
        # ambiguity errors surface before any network round-trip.
        if sensor_instconfig is None:
            sensor_instconfig = nrl.resolve_sensor(
                manufacturer=sensor_manufacturer,
                model=sensor_model,
                keys=sensor_keys,
            ).instconfig

        wants_datalogger = (
            datalogger_manufacturer or datalogger_model or datalogger_keys
        )
        if datalogger_instconfig is None and wants_datalogger:
            datalogger_instconfig = nrl.resolve_datalogger(
                manufacturer=datalogger_manufacturer,
                model=datalogger_model,
                keys=datalogger_keys,
            ).instconfig

        saved_paths = _build_outputs(
            nrl,
            sensor_instconfig=sensor_instconfig,
            datalogger_instconfig=datalogger_instconfig,
            output=output,
            format=format,
            compress=compress,
            network=network,
            station=station,
            location=location,
            channels=channels,
            merge=merge_channels,
            starttime=starttime,
            endtime=endtime,
        )
    except NrlxError as exc:
        _fail(exc)

    files = "\n".join(f"File: {path}" for path in saved_paths)
    _success(
        f"Response built\n\n"
        f"{files}\n"
        f"Format: {format.value}{'.zip' if compress else ''}"
    )

def _build_outputs(
    nrl: Nrlx,
    *,
    sensor_instconfig: str,
    datalogger_instconfig: str | None,
    output: Path,
    format: ResponseFormat,
    compress: bool,
    network: str | None,
    station: str | None,
    location: str | None,
    channels: list[str] | None,
    merge: bool,
    starttime: str | None,
    endtime: str | None,
) -> list[Path]:
    """Fetch and write the requested response file(s), one per channel label.

    The /combine endpoint labels one channel per request, so several channels
    mean several requests: written as channel-suffixed files by default, or
    merged into a single StationXML inventory with ``merge``.


    """
    if merge:
        if not channels or len(channels) < 2:
            raise NrlxError("--merge-channels needs at least two --channels values.")
        if format is not ResponseFormat.STATIONXML or compress:
            raise NrlxError(
                "--merge-channels only works with --format stationxml and no --zip."
            )

    def build_one(channel_label: str | None) -> BuiltResponse:
        return nrl.combine(
            sensor_instconfig=sensor_instconfig,
            datalogger_instconfig=datalogger_instconfig,
            format=format,
            compress=compress,
            network=network,
            station=station,
            location=location,
            channel=channel_label,
            starttime=starttime,
            endtime=endtime,
        )

    if merge:
        assert channels is not None  # guaranteed by the guard above
        blobs = [build_one(ch).content for ch in channels]
        merged = BuiltResponse(
            content=merge_stationxml(blobs),
            format=format,
            instconfig=sensor_instconfig,
        )
        return [merged.save(output)]

    if not channels or len(channels) == 1:
        only = channels[0] if channels else None
        return [build_one(only).save(output)]

    # Several channels, no merge: one request and one suffixed file each.
    return [
        build_one(ch).save(output.with_stem(f"{output.stem}_{ch}"))
        for ch in channels
    ]

_SEVERITY_STYLE = {
    Severity.OK: "green",
    Severity.WARNING: "yellow",
    Severity.ERROR: "bold red"
}

@app.command()
def doctor(
    file: Annotated[
        Path,
        typer.Argument(help="Response file to check."),
    ],
    format: Annotated[
        ResponseFormat | None,
        typer.Option(
            "--format",
            help="Response format. Inferred from the file extension if omitted.",
        ),
    ] = None
) -> None:
    """Run structural health checks on a saved response file."""

    try:
        resolved_format = format or infer_format(file)
        report = HealthReport.from_file(file, resolved_format)
    except NrlxError as exc:
        _fail(exc)

    table = Table(title=f"Health check: {file}")
    table.add_column("Severity")
    table.add_column("Finding")

    for finding in report.findings:
        style = _SEVERITY_STYLE[finding.severity]
        severity_label = f"[{style}]{finding.severity.value.upper()}[/{style}]"
        table.add_row(severity_label, finding.message)

    console.print(table)

    if not report.ok:
        raise typer.Exit(code=1)
