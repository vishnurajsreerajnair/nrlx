"""The nrlx command, with its subcommands"""

from __future__ import annotations

from typing import Annotated

import typer

import nrlx
from nrlx.tools.cmd.catalog import prefixes, status, sync
from nrlx.tools.cmd.convert import convert
from nrlx.tools.cmd.doctor import doctor
from nrlx.tools.cmd.local import local_app
from nrlx.tools.cmd.response import response

app = typer.Typer(
    name="nrlx",
    help="NRL eXtended: seismic instrument response tools.",
    no_args_is_help=True,
    add_completion=False,
)


def printversion(value: bool) -> None:
    """Print the version and exit, for the -j/--version flag"""
    if value:
        typer.echo(nrlx.__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option(
            "-j",
            "--version",
            callback=printversion,
            is_eager=True,
            help="Print the version and exit.",
        ),
    ] = False,
) -> None:
    """Run nrlx from the command line."""


app.command()(status)
app.command()(sync)
app.command()(prefixes)
app.command()(response)
app.command()(convert)
app.command()(doctor)
app.add_typer(local_app, name="local")
