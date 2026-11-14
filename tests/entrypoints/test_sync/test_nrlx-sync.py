from __future__ import annotations

from typer.testing import CliRunner

from nrlx.io.cache import get_catalog_file
from nrlx.tools.cmd import app

runner = CliRunner()


def test_sync(tmp_path, fake_service, catalog_content):
    fake_service.contents["catalog"] = catalog_content

    result = runner.invoke(app, ["sync", "--cache-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "Configurations: 5" in result.output
    assert get_catalog_file(tmp_path).read_bytes() == catalog_content


def test_sync_invalid_download_keeps_the_previous_catalog(
    cache_root, fake_service, catalog_content
):
    fake_service.contents["catalog"] = b"<html>maintenance</html>"

    result = runner.invoke(app, ["sync", "--cache-root", str(cache_root)])

    assert result.exit_code == 1
    assert "Invalid catalog" in result.output
    assert get_catalog_file(cache_root).read_bytes() == catalog_content


def test_sync_unreachable_service(tmp_path, fake_service):
    fake_service.status_code = 503

    result = runner.invoke(app, ["sync", "--cache-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "NRL service request failed" in result.output
    assert not get_catalog_file(tmp_path).exists()
