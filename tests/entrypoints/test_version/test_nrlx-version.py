from __future__ import annotations

import pytest
from typer.testing import CliRunner

import nrlx
from nrlx.tools.cmd import app

runner = CliRunner()


@pytest.mark.parametrize("flag", ["-j", "--version"])
def test_version(flag):
    result = runner.invoke(app, [flag])

    assert result.exit_code == 0
    assert result.output.strip() == nrlx.__version__


def test_no_arguments_prints_the_help():
    result = runner.invoke(app, [])

    assert "Usage" in result.output
    for command in ["status", "sync", "prefixes", "browse", "build", "doctor"]:
        assert command in result.output
