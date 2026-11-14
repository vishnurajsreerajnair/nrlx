from __future__ import annotations

from typer.testing import CliRunner

from nrlx.tools.cmd import app

runner = CliRunner()


def test_browse_without_catalog_says_sync(tmp_path):
    result = runner.invoke(app, ["browse", "--cache-root", str(tmp_path), "summary"])

    assert result.exit_code == 1
    assert "not found" in result.output
    assert "nrlx sync" in result.output


def test_browse_invalid_catalog(tmp_path):
    (tmp_path / "nrl").mkdir()
    (tmp_path / "nrl" / "catalog.json").write_text("{not json")

    result = runner.invoke(app, ["browse", "--cache-root", str(tmp_path), "summary"])

    assert result.exit_code == 1
    assert "Invalid catalog file" in result.output


def test_browse_summary(cache_root):
    result = runner.invoke(app, ["browse", "--cache-root", str(cache_root), "summary"])

    assert result.exit_code == 0
    assert "Configurations" in result.output
    assert "1.0" in result.output


def test_browse_elements(cache_root):
    result = runner.invoke(app, ["browse", "--cache-root", str(cache_root), "elements"])

    assert result.exit_code == 0
    assert "sensor" in result.output
    assert "datalogger" in result.output


def test_browse_manufacturers_positional_query(cache_root):
    result = runner.invoke(
        app, ["browse", "--cache-root", str(cache_root), "manufacturers", "streck"]
    )

    assert result.exit_code == 0
    assert "Streckeisen" in result.output
    assert "Nanometrics" not in result.output


def test_browse_models_by_manufacturer(cache_root):
    result = runner.invoke(
        app,
        [
            "browse",
            "--cache-root",
            str(cache_root),
            "models",
            "--manufacturer",
            "streckeisen",
        ],
    )

    assert result.exit_code == 0
    assert "STS-2" in result.output
    assert "STS-1" in result.output
    assert "Trillium" not in result.output


def test_browse_configs_query_searches_parameters(cache_root):
    result = runner.invoke(
        app, ["browse", "--cache-root", str(cache_root), "configs", "40Vpp"]
    )

    assert result.exit_code == 0
    assert "Quanterra" in result.output
    assert "Streckeisen" not in result.output


def test_browse_show_renders_the_parameters(cache_root):
    result = runner.invoke(
        app,
        [
            "browse",
            "--cache-root",
            str(cache_root),
            "show",
            "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel",
        ],
    )

    assert result.exit_code == 0
    assert "Sensitivity" in result.output
    assert "1500 V/m/s" in result.output


def test_browse_show_unique_substring(cache_root):
    result = runner.invoke(
        app, ["browse", "--cache-root", str(cache_root), "show", "SG750"]
    )

    assert result.exit_code == 0
    assert "750 V/m/s" in result.output


def test_browse_show_missing_instconfig(cache_root):
    result = runner.invoke(
        app, ["browse", "--cache-root", str(cache_root), "show", "does_not_exist"]
    )

    assert result.exit_code == 1
    assert "No configuration matches" in result.output


def test_browse_show_ambiguous_substring(cache_root):
    # a substring of both STS-2 configurations, exact for neither
    result = runner.invoke(
        app, ["browse", "--cache-root", str(cache_root), "show", "STS-2"]
    )

    assert result.exit_code == 1
    assert "Ambiguous" in result.output
