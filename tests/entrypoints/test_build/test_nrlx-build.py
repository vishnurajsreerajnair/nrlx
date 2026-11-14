from __future__ import annotations

from typer.testing import CliRunner

from nrlx.io.inventory import read_stationxml
from nrlx.tools.cmd import app

runner = CliRunner()


def test_build_writes_the_file(cache_root, tmp_path, fake_service):
    fake_service.contents["combine"] = b"<xml/>"
    output = tmp_path / "out.xml"

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.read_bytes() == b"<xml/>"
    assert "sensor_Streckeisen_STS-1_LP360" in result.output


def test_build_ambiguous_selection(cache_root, tmp_path, fake_service):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-manufacturer",
            "Streckeisen",
            "--sensor-model",
            "STS-2",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "Ambiguous" in result.output
    assert fake_service.requests == []


def test_build_repeated_key_flags_resolve_uniquely(cache_root, tmp_path, fake_service):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            # STS-2 alone is ambiguous, SG750 settles it
            "--sensor-key",
            "STS-2",
            "--sensor-key",
            "SG750",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    assert fake_service.requests[0].params["instconfig"] == (
        "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel"
    )


def test_build_comma_separated_keys_with_datalogger(cache_root, tmp_path, fake_service):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-keys",
            "STS-2, SG750",
            "--datalogger-keys",
            "Q330,40Vpp",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    assert fake_service.requests[0].params["instconfig"] == (
        "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel"
        ":datalogger_Quanterra_Q330_FV40Vpp_FR100"
    )


def test_build_instconfig_and_filters_are_rejected(cache_root, tmp_path):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--sensor-model",
            "STS-1",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "not both" in result.output


def test_build_comma_separated_channels_write_a_file_each(
    cache_root, tmp_path, fake_service
):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--channels",
            "EHZ,EHN,EHE",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    for code in ["EHZ", "EHN", "EHE"]:
        assert (tmp_path / f"out_{code}.xml").exists()
    assert not (tmp_path / "out.xml").exists()


def test_build_repeated_channel_flags_write_a_file_each(
    cache_root, tmp_path, fake_service
):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--channel",
            "HHZ",
            "--channel",
            "HHN",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / "out_HHZ.xml").exists()
    assert (tmp_path / "out_HHN.xml").exists()


def test_build_single_channel_writes_the_output(cache_root, tmp_path, fake_service):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--channel",
            "HHZ",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 0
    assert (tmp_path / "out.xml").exists()
    assert fake_service.requests[0].params["channel"] == "HHZ"


def test_build_merged_channels(cache_root, tmp_path, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("EHZ")
    output = tmp_path / "station.xml"

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--channels",
            "EHZ,EHN,EHE",
            "--merge-channels",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert len(read_stationxml(output.read_bytes())[0][0].channels) == 3


def test_build_merge_needs_two_channels(cache_root, tmp_path):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--merge-channels",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "at least two" in result.output


def test_build_merge_rejects_non_stationxml(cache_root, tmp_path):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--format",
            "resp",
            "--merge-channels",
            "--channel",
            "HHZ",
            "--channel",
            "HHN",
            "--output",
            str(tmp_path / "out.resp"),
        ],
    )

    assert result.exit_code == 1
    assert "stationxml" in result.output


def test_build_unreachable_service(cache_root, tmp_path, fake_service):
    fake_service.status_code = 503

    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "NRL service request failed" in result.output
    assert not (tmp_path / "out.xml").exists()


def test_build_without_catalog_says_sync(tmp_path):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(tmp_path),
            "--sensor-keys",
            "STS-1",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "nrlx sync" in result.output


def test_build_with_coordinates(cache_root, tmp_path, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("EHZ")
    output = tmp_path / "station.xml"

    # a negative longitude is read as a value, not as an option
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--latitude",
            "49.096",
            "--longitude",
            "-8.432",
            "--elevation",
            "112",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    station = read_stationxml(output.read_bytes())[0][0]
    assert (station.latitude, station.longitude, station.elevation) == (
        49.096,
        -8.432,
        112.0,
    )


def test_build_rejects_a_latitude_alone(cache_root, tmp_path, fake_service):
    result = runner.invoke(
        app,
        [
            "build",
            "--cache-root",
            str(cache_root),
            "--sensor-instconfig",
            "sensor_Streckeisen_STS-1_LP360",
            "--latitude",
            "49.096",
            "--output",
            str(tmp_path / "out.xml"),
        ],
    )

    assert result.exit_code == 1
    assert "go together" in result.output
    assert fake_service.requests == []
