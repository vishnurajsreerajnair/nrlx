"""Command checking the response files: nrlx doctor"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from nrlx.core.doctor import check_response, infer_format
from nrlx.schema.response import ResponseFormat

console = Console()
errconsole = Console(stderr=True)


def doctor(
    file: Annotated[
        Path,
        typer.Argument(help="Response file to check."),
    ],
    response_format: Annotated[
        ResponseFormat | None,
        typer.Option(
            "--format",
            help="Response format. Inferred from the file extension if omitted.",
        ),
    ] = None,
) -> None:
    """Run structural health checks on a saved response file."""
    # the format from the extension when not given
    try:
        if response_format is None:
            response_format = infer_format(file)
        content = file.read_bytes()
    except (OSError, ValueError) as err:
        errconsole.print(f"[bold red]Error:[/bold red] {escape(str(err))}")
        raise typer.Exit(code=1) from err

    findings = check_response(content, response_format)

    table = Table(title=f"Health check: {escape(str(file))}")
    table.add_column("Severity")
    table.add_column("Finding")

    for severity, message in findings:
        match severity:
            case "ok":
                style = "green"
            case "warning":
                style = "yellow"
            case "error":
                style = "bold red"
        table.add_row(
            f"[{style}]{severity.upper()}[/{style}]",
            escape(message),
        )

    console.print(table)

    # an error fails the check
    if any(severity == "error" for severity, _ in findings):
        raise typer.Exit(code=1)
