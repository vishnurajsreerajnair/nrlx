from __future__ import annotations

import json

from typer.testing import CliRunner

from nrlx.tools.cmd import app

runner = CliRunner()

PREFIXES = [
    {
        "prefix": "LP",
        "description": "Long-Period_Corner",
        "question": "What is the long-period corner?",
    },
    {
        "prefix": "FR",
        "description": "Final_Sample_Rate",
        "question": "What is the final sample rate?",
    },
]


def test_prefixes_renders_the_code_table(fake_service):
    fake_service.contents["prefix-lookup"] = json.dumps(PREFIXES).encode()

    result = runner.invoke(app, ["prefixes"])

    assert result.exit_code == 0
    assert "Long-Period Corner" in result.output
    assert "Final Sample Rate" in result.output
    assert fake_service.requests[0].params == {"format": "json", "nodata": 404}


def test_prefixes_query_filters_by_prefix_or_meaning(fake_service):
    fake_service.contents["prefix-lookup"] = json.dumps(PREFIXES).encode()

    byprefix = runner.invoke(app, ["prefixes", "LP"])
    bymeaning = runner.invoke(app, ["prefixes", "sample"])

    assert "Long-Period Corner" in byprefix.output
    assert "Final Sample Rate" not in byprefix.output
    assert "Final Sample Rate" in bymeaning.output
    assert "Long-Period Corner" not in bymeaning.output


def test_prefixes_invalid_table(fake_service):
    fake_service.contents["prefix-lookup"] = b'{"not": "a list"}'

    result = runner.invoke(app, ["prefixes"])

    assert result.exit_code == 1
    assert "Invalid prefix table" in result.output
