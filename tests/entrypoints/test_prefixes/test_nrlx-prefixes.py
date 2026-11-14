from __future__ import annotations

from typer.testing import CliRunner

from nrlx.io.cache import get_prefixes_file
from nrlx.tools.cmd import app

runner = CliRunner()


def test_prefixes_renders_the_code_table_without_requests(cache_root, fake_service):
    result = runner.invoke(app, ["prefixes", "--cache-root", str(cache_root)])

    assert result.exit_code == 0
    assert "Long-Period Corner" in result.output
    assert "Final Sample Rate" in result.output
    assert "What is the final sample rate?" in result.output
    assert fake_service.requests == []


def test_prefixes_query_filters_by_prefix_or_meaning(cache_root):
    byprefix = runner.invoke(app, ["prefixes", "LP", "--cache-root", str(cache_root)])
    bymeaning = runner.invoke(
        app, ["prefixes", "sample", "--cache-root", str(cache_root)]
    )

    assert "Long-Period Corner" in byprefix.output
    assert "Final Sample Rate" not in byprefix.output
    assert "Final Sample Rate" in bymeaning.output
    assert "Long-Period Corner" not in bymeaning.output


def test_prefixes_before_sync_says_sync(tmp_path):
    result = runner.invoke(app, ["prefixes", "--cache-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "Run 'nrlx sync'" in result.output


def test_prefixes_invalid_table(cache_root):
    get_prefixes_file(cache_root).write_bytes(b'{"not": "a list"}')

    result = runner.invoke(app, ["prefixes", "--cache-root", str(cache_root)])

    assert result.exit_code == 1
    assert "Invalid code table" in result.output
