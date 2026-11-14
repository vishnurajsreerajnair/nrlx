"""The nrlx command, with its subcommands"""

from __future__ import annotations

from typing import Annotated

import typer

import nrlx
from nrlx.tools.cmd.browse import app as browseapp
from nrlx.tools.cmd.build import build
from nrlx.tools.cmd.catalog import prefixes, status, sync
from nrlx.tools.cmd.doctor import doctor

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
app.add_typer(browseapp, name="browse")
app.command()(build)
app.command()(doctor)
