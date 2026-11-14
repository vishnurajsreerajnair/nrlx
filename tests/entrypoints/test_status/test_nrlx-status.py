from __future__ import annotations

from typer.testing import CliRunner

import nrlx
from nrlx.tools.cmd import app

runner = CliRunner()


def test_status_shows_version_and_cache(cache_root):
    result = runner.invoke(app, ["status", "--cache-root", str(cache_root)])

    assert result.exit_code == 0
    assert nrlx.__version__ in result.output
    assert "True" in result.output


def test_status_live_shows_the_service_version(tmp_path, fake_service):
    fake_service.contents["version"] = b"1.0.9\n"

    result = runner.invoke(app, ["status", "--cache-root", str(tmp_path), "--live"])

    assert result.exit_code == 0
    assert "Yes" in result.output
    assert "1.0.9" in result.output
    assert fake_service.requests[0].url.endswith("/version")


def test_status_live_unreachable_service(tmp_path, fake_service):
    fake_service.status_code = 503

    result = runner.invoke(app, ["status", "--cache-root", str(tmp_path), "--live"])

    assert result.exit_code == 1
    assert "No" in result.output
    assert "NRL service request failed" in result.output
