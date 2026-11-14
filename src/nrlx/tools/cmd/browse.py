"""Commands browsing the local catalog: nrlx browse ..."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from nrlx.io.cache import get_catalog_file, read_catalog
from nrlx.models.catalog import Catalog

console = Console()
errconsole = Console(stderr=True)

app = typer.Typer(help="Browse the locally cached NRL catalog.")


@app.callback()
def main(
    ctx: typer.Context,
    cache_root: Annotated[
        Path | None,
        typer.Option("--cache-root", help="Custom cache root directory."),
    ] = None,
) -> None:
    """Browse the locally cached NRL catalog."""
    # the catalog is read once for the subcommand, in the context
    try:
        ctx.obj = read_catalog(get_catalog_file(cache_root))
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err


@app.command("summary")
def summary(ctx: typer.Context) -> None:
    """Show catalog-wide counts."""
    catalog: Catalog = ctx.obj

    table = Table(title="NRL catalog summary")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Format version", str(catalog.format_version))
    table.add_row("Element groups", str(len(catalog.get_elements())))
    table.add_row("Manufacturers", str(len(catalog.get_manufacturers())))
    table.add_row("Models", str(len(catalog.get_models())))
    table.add_row("Configurations", str(len(catalog.get_configurations())))

    console.print(table)


@app.command("elements")
def elements(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by element name, for example sensor."),
    ] = None,
) -> None:
    """List top-level element groups, for example sensor and datalogger."""
    catalog: Catalog = ctx.obj

    table = Table(title="NRL catalog elements")
    table.add_column("Element")
    table.add_column("Manufacturers", justify="right")
    table.add_column("Models", justify="right")
    table.add_column("Configurations", justify="right")

    for element in catalog.get_elements(query):
        models = [
            model
            for manufacturer in element.manufacturers
            for model in manufacturer.models
        ]
        configurations = [
            configuration for model in models for configuration in model.configurations
        ]
        table.add_row(
            element.name,
            str(len(element.manufacturers)),
            str(len(models)),
            str(len(configurations)),
        )

    console.print(table)


@app.command("manufacturers")
def manufacturers(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by manufacturer name."),
    ] = None,
    element_name: Annotated[
        str | None,
        typer.Option("--element", help="Filter by element group, for example sensor."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=1000, help="Maximum rows to display."),
    ] = 50,
) -> None:
    """List manufacturers."""
    catalog: Catalog = ctx.obj

    table = Table(title="NRL catalog manufacturers")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Models", justify="right")
    table.add_column("Configurations", justify="right")

    for element, manufacturer in catalog.get_manufacturers(element_name, query)[:limit]:
        configurations = [
            configuration
            for model in manufacturer.models
            for configuration in model.configurations
        ]
        table.add_row(
            element.name,
            manufacturer.name,
            str(len(manufacturer.models)),
            str(len(configurations)),
        )

    console.print(table)


@app.command("models")
def models(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(help="Filter by model name."),
    ] = None,
    element_name: Annotated[
        str | None,
        typer.Option("--element", help="Filter by element group, for example sensor."),
    ] = None,
    manufacturer_name: Annotated[
        str | None,
        typer.Option("--manufacturer", help="Filter by manufacturer name."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=1000, help="Maximum rows to display."),
    ] = 50,
) -> None:
    """List models."""
    catalog: Catalog = ctx.obj

    table = Table(title="NRL catalog models")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Model")
    table.add_column("Configurations", justify="right")

    for element, manufacturer, model in catalog.get_models(
        element_name, manufacturer_name, query
    )[:limit]:
        table.add_row(
            element.name,
            manufacturer.name,
            model.name,
            str(len(model.configurations)),
        )

    console.print(table)


@app.command("configs")
def configs(
    ctx: typer.Context,
    query: Annotated[
        str | None,
        typer.Argument(
            help="Free-text search across manufacturer, model, and instconfig."
        ),
    ] = None,
    element_name: Annotated[
        str | None,
        typer.Option("--element", help="Filter by element group, for example sensor."),
    ] = None,
    manufacturer_name: Annotated[
        str | None,
        typer.Option("--manufacturer", help="Filter by manufacturer name."),
    ] = None,
    model_name: Annotated[
        str | None,
        typer.Option("--model", help="Filter by model name."),
    ] = None,
    instconfig: Annotated[
        str | None,
        typer.Option("--instconfig", help="Filter by instconfig substring."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=1000, help="Maximum rows to display."),
    ] = 50,
) -> None:
    """List response configurations.

    Pass a free-text QUERY to search manufacturer, model, and instconfig at
    once (e.g. 'nrlx browse configs lunitek'). Without QUERY, --element/
    --manufacturer/--model/--instconfig narrow the listing precisely instead.


    """
    catalog: Catalog = ctx.obj

    # the query searches every field, the filters narrow each their own field
    if query is not None:
        rows = catalog.get_configurations(element_name, keys=[query])
    else:
        rows = catalog.get_configurations(
            element_name, manufacturer_name, model_name, instconfig
        )

    table = Table(title="NRL catalog configurations")
    table.add_column("Element")
    table.add_column("Manufacturer")
    table.add_column("Model")
    table.add_column("Instconfig")
    table.add_column("Version")

    for element, manufacturer, model, configuration in rows[:limit]:
        table.add_row(
            element.name,
            manufacturer.name,
            model.name,
            configuration.instconfig,
            configuration.version,
        )

    console.print(table)


@app.command("show")
def show(
    ctx: typer.Context,
    instconfig: Annotated[
        str,
        typer.Argument(help="Instconfig to inspect (exact, or a unique substring)."),
    ],
) -> None:
    """Show one configuration in full: description and every parameter.

    The list views (configs/models/...) stay narrow on purpose; this is where
    you see a configuration's parameters - Sensitivity, Sensor_Type, corner
    period, and so on - so you know which values you can pass as build keys.


    """
    catalog: Catalog = ctx.obj

    # the exact instconfig wins over the longer ones containing it
    rows = catalog.get_configurations(instconfig=instconfig)
    exactrows = [
        (element, manufacturer, model, configuration)
        for element, manufacturer, model, configuration in rows
        if configuration.instconfig == instconfig
    ]

    match exactrows or rows:
        case [(element, manufacturer, model, configuration)]:
            table = Table(title=escape(configuration.instconfig))
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Element", element.name)
            table.add_row("Manufacturer", manufacturer.name)
            table.add_row("Model", model.name)
            table.add_row("Version", configuration.version)
            if configuration.description:
                table.add_row("Description", escape(configuration.description))
            for name, value in configuration.parameters.items():
                table.add_row(escape(name), escape(value))
            console.print(table)
        case []:
            errconsole.print(
                "[bold red]Error:[/bold red] No configuration matches instconfig: "
                f"{escape(instconfig)}"
            )
            raise typer.Exit(code=1)
        case _:
            listed = "\n".join(
                f"  {configuration.instconfig}" for _, _, _, configuration in rows[:20]
            )
            errconsole.print(
                f"[bold red]Error:[/bold red] Ambiguous: {len(rows)} configurations "
                f"match '{escape(instconfig)}'.\n{escape(listed)}"
            )
            raise typer.Exit(code=1)
