from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from nrlx import __version__
from nrlx.cli import app

runner = CliRunner()

_VALID_STATIONXML = b"""<?xml version="1.0"?>
<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
  <Network code="XX"><Station code="YY"><Channel code="ZZZ" locationCode="00">
    <Response><InstrumentSensitivity><Value>1.0</Value></InstrumentSensitivity></Response>
  </Channel></Station></Network>
</FDSNStationXML>
"""


def _config(
    instconfig: str, parameters: dict[str, str] | None = None
) -> dict[str, Any]:
    data: dict[str, Any] = {"instconfig": instconfig, "version": "1"}
    if parameters:
        data["parameters"] = parameters
    return data


def _catalog_dict() -> dict[str, Any]:
    sensor = {
        "name": "sensor",
        "manufacturer": [
            {
                "name": "Streckeisen",
                "model": [
                    {
                        "name": "STS-2",
                        "configuration": [
                            _config(
                                "sensor_Streckeisen_STS-2_A",
                                {"Sensitivity": "1500 V/m/s"},
                            ),
                            _config("sensor_Streckeisen_STS-2_B"),
                        ],
                    }
                ],
            }
        ],
    }
    datalogger = {
        "name": "datalogger",
        "manufacturer": [
            {
                "name": "Quanterra",
                "model": [
                    {
                        "name": "Q330",
                        "configuration": [_config("datalogger_Quanterra_Q330_A")],
                    }
                ],
            }
        ],
    }
    return {
        "NRLCatalog": {
            "formatversion": 1.0,
            "element": [sensor, datalogger],
        }
    }


def _seed_catalog(cache_root: Path) -> None:
    """Write a catalog into the cache layout the CLI expects."""
    nrl_dir = cache_root / "nrl"
    nrl_dir.mkdir(parents=True, exist_ok=True)
    (nrl_dir / "catalog.json").write_text(json.dumps(_catalog_dict()), encoding="utf-8")


class _FakeResponse:
    status_code = 200

    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


def test_status_shows_version(tmp_path):
    result = runner.invoke(app, ["status", "--cache-root", str(tmp_path)])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_browse_summary_without_catalog_errors(tmp_path):
    result = runner.invoke(app, ["browse", "--cache-root", str(tmp_path), "summary"])

    assert result.exit_code == 1
    assert "not found" in result.output


def test_browse_summary_with_catalog(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(app, ["browse", "--cache-root", str(tmp_path), "summary"])

    assert result.exit_code == 0
    assert "Configurations" in result.output


def test_browse_manufacturers_positional_query(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(
        app, ["browse", "--cache-root", str(tmp_path), "manufacturers", "streck"]
    )

    assert result.exit_code == 0
    assert "Streckeisen" in result.output


def test_browse_show_renders_parameters(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(
        app,
        [
            "browse", "--cache-root", str(tmp_path),
            "show", "sensor_Streckeisen_STS-2_A",
        ],
    )

    assert result.exit_code == 0
    assert "Sensitivity" in result.output
    assert "1500 V/m/s" in result.output


def test_browse_show_missing_instconfig_errors(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(
        app,
        ["browse", "--cache-root", str(tmp_path), "show", "does_not_exist"],
    )

    assert result.exit_code == 1
    assert "No configuration matches" in result.output


def test_browse_show_ambiguous_substring_errors(tmp_path):
    _seed_catalog(tmp_path)

    # "STS-2" is a substring of both fixture configs, and an exact match of
    # neither -> ambiguous.
    result = runner.invoke(
        app,
        ["browse", "--cache-root", str(tmp_path), "show", "STS-2"],
    )

    assert result.exit_code == 1
    assert "Ambiguous" in result.output


def test_doctor_good_file(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(_VALID_STATIONXML)

    result = runner.invoke(app, ["doctor", str(path)])

    assert result.exit_code == 0


def test_doctor_missing_file_errors(tmp_path):
    result = runner.invoke(app, ["doctor", str(tmp_path / "missing.xml")])

    assert result.exit_code == 1


def test_doctor_html_as_xml_errors(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(b"<html><body>404</body></html>")

    result = runner.invoke(app, ["doctor", str(path)])

    assert result.exit_code == 1


def test_build_ambiguous_selection_errors(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-manufacturer", "Streckeisen",
            "--sensor-model", "STS-2",
            "--output", str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "Ambiguous" in result.output


def test_build_happy_path_writes_file(tmp_path, monkeypatch):
    _seed_catalog(tmp_path)
    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _FakeResponse(b"<xml/>"),
    )
    output = tmp_path / "out.xml"

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-instconfig", "sensor_Streckeisen_STS-2_A",
            "--output", str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.read_bytes() == b"<xml/>"


def test_build_with_repeated_key_flags_resolves_uniquely(tmp_path, monkeypatch):
    _seed_catalog(tmp_path)
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(b"<xml/>")

    monkeypatch.setattr("nrlx.client.httpx.get", fake_get)
    output = tmp_path / "out.xml"

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            # "STS-2" alone is ambiguous in the fixture; the _B key settles it.
            "--sensor-key", "STS-2",
            "--sensor-key", "_B",
            "--output", str(output),
        ],
    )

    assert result.exit_code == 0
    assert captured["params"]["instconfig"] == "sensor_Streckeisen_STS-2_B"


def test_build_with_comma_separated_keys_resolves_uniquely(tmp_path, monkeypatch):
    _seed_catalog(tmp_path)
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(b"<xml/>")

    monkeypatch.setattr("nrlx.client.httpx.get", fake_get)

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-keys", "STS-2,_B",
            "--output", str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    assert captured["params"]["instconfig"] == "sensor_Streckeisen_STS-2_B"


def test_build_with_comma_separated_channels_writes_one_file_each(
    tmp_path, monkeypatch
):
    _seed_catalog(tmp_path)
    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _FakeResponse(b"<xml/>"),
    )

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-instconfig", "sensor_Streckeisen_STS-2_A",
            "--channels", "EHZ,EHN,EHE",
            "--output", str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    for code in ("EHZ", "EHN", "EHE"):
        assert (tmp_path / f"out_{code}.xml").exists()


def test_build_multiple_channels_writes_one_file_each(tmp_path, monkeypatch):
    _seed_catalog(tmp_path)
    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _FakeResponse(b"<xml/>"),
    )

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-instconfig", "sensor_Streckeisen_STS-2_A",
            "--channel", "HHZ",
            "--channel", "HHN",
            "--output", str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / "out_HHZ.xml").exists()
    assert (tmp_path / "out_HHN.xml").exists()


def test_build_merge_needs_two_channels(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-instconfig", "sensor_Streckeisen_STS-2_A",
            "--merge-channels",
            "--output", str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "at least two" in result.output


def test_build_merge_rejects_non_stationxml(tmp_path):
    _seed_catalog(tmp_path)

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-instconfig", "sensor_Streckeisen_STS-2_A",
            "--format", "resp",
            "--merge-channels",
            "--channel", "HHZ",
            "--channel", "HHN",
            "--output", str(tmp_path / "out.resp"),
        ],
    )

    assert result.exit_code == 1
    assert "stationxml" in result.output


@pytest.mark.skipif(
    importlib.util.find_spec("obspy") is not None, reason="obspy is installed here"
)
def test_build_merge_without_obspy_prints_intact_install_hint(tmp_path, monkeypatch):
    _seed_catalog(tmp_path)
    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _FakeResponse(b"<xml/>"),
    )

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root", str(tmp_path),
            "--sensor-instconfig", "sensor_Streckeisen_STS-2_A",
            "--merge-channels",
            "--channel", "HHZ",
            "--channel", "HHN",
            "--output", str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    # Rich must not eat "[obspy]" as a markup tag (regression test).
    assert "nrlx[obspy]" in result.output


def test_prefixes_renders_code_table(monkeypatch):
    class _FakeJsonResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> list[dict[str, str]]:
            return [
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

    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _FakeJsonResponse(),
    )

    result = runner.invoke(app, ["prefixes"])

    assert result.exit_code == 0
    assert "Long-Period Corner" in result.output
    assert "Final Sample Rate" in result.output

    filtered = runner.invoke(app, ["prefixes", "LP"])
    assert "Long-Period Corner" in filtered.output
    assert "Final Sample Rate" not in filtered.output


def test_sync_happy_path(tmp_path, monkeypatch):
    catalog_bytes = json.dumps(_catalog_dict()).encode("utf-8")
    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _FakeResponse(catalog_bytes),
    )

    result = runner.invoke(app, ["sync", "--cache-root", str(tmp_path)])

    assert result.exit_code == 0
    assert (tmp_path / "nrl" / "catalog.json").read_bytes() == catalog_bytes
