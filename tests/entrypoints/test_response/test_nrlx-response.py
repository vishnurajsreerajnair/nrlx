from __future__ import annotations

import json
from pathlib import Path

import obspy
import pytest
from typer.testing import CliRunner

from nrlx.tools.cmd import app

runner = CliRunner()

DATA_DIR = Path(__file__).parents[2] / "data"

SENSOR = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
DATALOGGER = "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def test_response_without_keys_shows_the_catalog(cache_root, fake_service):
    result = runner.invoke(app, ["response", "--cache-root", str(cache_root)])

    assert result.exit_code == 0
    assert "NRL catalog" in result.output
    assert "Streckeisen" in result.output
    assert "Quanterra" in result.output
    assert fake_service.requests == []


def test_response_tree_leaves_out_the_manufacturers_without_models(cache_root):
    catalogfile = cache_root / "nrl" / "catalog.json"
    content = json.loads(catalogfile.read_bytes())
    sensors = content["NRLCatalog"]["element"][0]
    sensors["manufacturer"].append({"name": "EmptyMaker", "model": []})
    catalogfile.write_text(json.dumps(content))

    result = runner.invoke(app, ["response", "--cache-root", str(cache_root)])

    assert result.exit_code == 0
    assert "Streckeisen" in result.output
    assert "EmptyMaker" not in result.output


def test_response_bare_keys_list_the_rows_and_what_varies(cache_root):
    result = runner.invoke(
        app, ["response", "STS-2", "--cache-root", str(cache_root)], terminal_width=200
    )

    assert result.exit_code == 0
    assert "keys: 2 configurations" in result.output
    assert SENSOR in result.output
    assert "Still varying: SG 750 V/m/s, 1500 V/m/s" in result.output


def test_response_parts_that_are_unique_print_the_line_to_write(
    cache_root, fake_service
):
    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-2,SG=1500",
            "--datalogger",
            "Q330",
            "--channels",
            "HHZ",
            "--cache-root",
            str(cache_root),
        ],
        terminal_width=300,
    )

    assert result.exit_code == 0
    assert "Every part matches one configuration" in result.output
    assert (
        f"nrlx response --sensor {SENSOR} --datalogger {DATALOGGER} "
        "--channels HHZ -o FILE"
    ) in result.output
    assert fake_service.requests == []


def test_response_writes_one_stationxml_with_every_channel(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    output = tmp_path / "out" / "st.xml"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-2",
            "--sensor",
            "SG=1500",
            "--datalogger",
            "Q330",
            "--network",
            "XY",
            "--station",
            "TST",
            "--location",
            "00",
            "--channels",
            "HHZ,HHN,HHE",
            "--starttime",
            "2026-01-01",
            "-o",
            str(output),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Response written (stationxml)" in result.output
    [request] = fake_service.requests
    assert request.params is not None
    assert request.params["instconfig"] == f"{SENSOR}:{DATALOGGER}"
    channels = obspy.read_inventory(output)[0][0]
    assert [channel.code for channel in channels] == ["HHZ", "HHN", "HHE"]
    assert channels[0].start_date == obspy.UTCDateTime(2026, 1, 1)


def test_response_split_writes_one_resp_per_channel(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "--network",
            "XY",
            "--station",
            "TST",
            "--location",
            "",
            "--channels",
            "HHZ,HHN",
            "--split",
            "-o",
            str(tmp_path / "st.resp"),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in tmp_path.glob("st_*")) == [
        "st_XY.TST..HHN.resp",
        "st_XY.TST..HHZ.resp",
    ]
    text = (tmp_path / "st_XY.TST..HHZ.resp").read_text()
    assert "B052F04     Channel:     HHZ" in text


def test_response_format_overrides_the_extension(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    output = tmp_path / "st.txt"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "--format",
            "resp",
            "-o",
            str(output),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.read_text().startswith("#")


def test_response_unknown_extension_fails_before_any_request(
    cache_root, fake_service, tmp_path
):
    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "-o",
            str(tmp_path / "st.txt"),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 1
    assert "Cannot tell the format from .txt" in result.output
    assert fake_service.requests == []


def test_response_ambiguous_part_does_not_write(cache_root, fake_service, tmp_path):
    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-2",
            "-o",
            str(tmp_path / "st.xml"),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 1
    assert "Each part must match one configuration" in result.output
    assert fake_service.requests == []
    assert not (tmp_path / "st.xml").exists()


def test_response_no_match_gives_the_hints(cache_root):
    result = runner.invoke(
        app, ["response", "--sensor", "streckeisn", "--cache-root", str(cache_root)]
    )

    assert result.exit_code == 1
    assert "Did you mean Streckeisen?" in result.output


def test_response_bare_keys_with_parts_fail(cache_root):
    result = runner.invoke(
        app,
        ["response", "STS-2", "--sensor", "STS-1", "--cache-root", str(cache_root)],
    )

    assert result.exit_code == 1
    assert "Keys without a part only explore" in result.output


def test_response_writing_needs_a_part(cache_root, tmp_path):
    result = runner.invoke(
        app,
        ["response", "-o", str(tmp_path / "st.xml"), "--cache-root", str(cache_root)],
    )

    assert result.exit_code == 1
    assert "Writing needs a part" in result.output


def test_response_service_error(cache_root, fake_service, tmp_path):
    fake_service.status_code = 500

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "-o",
            str(tmp_path / "st.xml"),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 1
    assert "NRL service request failed" in result.output


def test_response_before_sync_says_sync(tmp_path):
    result = runner.invoke(app, ["response", "--cache-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "Run 'nrlx sync'" in result.output


def test_response_interactive_asks_prints_the_line_and_writes(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    output = tmp_path / "st.xml"

    # sensor only; Streckeisen; STS-2; 1500 V/m/s; the labels and the file
    answers = ["2", "2", "2", "2", "XY", "TST", "00", "HHZ,HHN", str(output)]
    result = runner.invoke(
        app,
        ["response", "-i", "--cache-root", str(cache_root)],
        input="\n".join([*answers, ""]),
        terminal_width=300,
    )

    assert result.exit_code == 0, result.output
    assert "Choice (1-5):" in result.output
    assert "[1/2" not in result.output
    assert "()" not in result.output
    assert (
        f"nrlx response --sensor {SENSOR} --network XY --station TST "
        f"--location 00 --channels HHZ,HHN -o {output}"
    ) in result.output
    channels = obspy.read_inventory(output)[0][0]
    assert [channel.code for channel in channels] == ["HHZ", "HHN"]


def test_response_interactive_takes_the_only_options(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    output = tmp_path / "dl.xml"

    # datalogger only: one manufacturer, one model, one configuration
    answers = ["3", "XY", "TST", "00", "HHZ", str(output)]
    result = runner.invoke(
        app,
        ["response", "-i", "--cache-root", str(cache_root)],
        input="\n".join([*answers, ""]),
        terminal_width=300,
    )

    assert result.exit_code == 0, result.output
    assert "Quanterra (the only one)" in result.output
    assert "Q330 (the only one)" in result.output
    assert f"--datalogger {DATALOGGER}" in result.output
    assert output.exists()


# parts from files
def test_response_sensor_file_with_datalogger_keys_prints_the_line(
    cache_root, fake_service
):
    sensor = DATA_DIR / "nrl_part_ea120.xml"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor-file",
            str(sensor),
            "--datalogger",
            "Q330",
            "--cache-root",
            str(cache_root),
        ],
        terminal_width=300,
    )

    assert result.exit_code == 0, result.output
    assert f"sensor: {sensor}, stages: 1, m/s**2 to V" in result.output
    assert "Every part matches one configuration" in result.output
    assert f"--datalogger {DATALOGGER} --sensor-file {sensor} -o FILE" in (
        result.output
    )
    assert fake_service.requests == []


def test_response_sensor_file_with_datalogger_keys_writes(
    cache_root, fake_service, tmp_path
):
    fake_service.contents["combine"] = (DATA_DIR / "nrl_part_q330hr.xml").read_bytes()
    output = tmp_path / "st.xml"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor-file",
            str(DATA_DIR / "nrl_part_ea120.xml"),
            "--datalogger",
            "Q330",
            "--channels",
            "HNZ",
            "-o",
            str(output),
            "--cache-root",
            str(cache_root),
        ],
        terminal_width=300,
    )

    # the datalogger asked alone, the Eentec normalization corrected
    assert result.exit_code == 0, result.output
    [request] = fake_service.requests
    assert request.params is not None
    assert request.params["instconfig"] == DATALOGGER
    assert "note: stage 1: normalization factor corrected by x1.99876" in (
        result.output
    )
    [channel] = obspy.read_inventory(output)[0][0]
    assert channel.code == "HNZ"
    assert channel.response.instrument_sensitivity.input_units == "m/s**2"


def test_response_two_files_write_without_the_service(
    cache_root, fake_service, tmp_path
):
    output = tmp_path / "st.resp"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor-file",
            str(DATA_DIR / "nrl_part_sts2.xml"),
            "--datalogger-file",
            str(DATA_DIR / "nrl_part_centaur.xml"),
            "-o",
            str(output),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert fake_service.requests == []
    assert "Response written (resp)" in result.output
    assert len(obspy.read_inventory(output)[0][0][0].response.response_stages) > 1


def test_response_file_picks_a_channel(cache_root, fake_service, tmp_path):
    # a file with two channels, the second with half the gain
    two = tmp_path / "two.xml"
    inventory = obspy.read_inventory(DATA_DIR / "nrl_part_sts2.xml")
    channel = inventory[0][0][0].copy()
    channel.code = "HHN"
    channel.response.response_stages[0].stage_gain /= 2.0
    inventory[0][0].channels.append(channel)
    inventory.write(str(two), format="STATIONXML")
    seedid = f"{inventory[0].code}.{inventory[0][0].code}.{channel.location_code}.HHN"
    arguments = ["response", "--datalogger", "Q330", "--cache-root", str(cache_root)]

    picked = runner.invoke(app, [*arguments, "--sensor-file", f"{two}#{seedid}"])
    several = runner.invoke(app, [*arguments, "--sensor-file", str(two)])

    assert picked.exit_code == 0, picked.output
    assert several.exit_code == 1
    assert "2 channels or epochs" in several.output


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (["--sensor", "STS-1", "--datalogger", "Q330"], "keys or by a response"),
        ([], "combined with the other part"),
        (["--integrated", "Q330"], "go as a sensor"),
        (["--datalogger", "Q330", "-i"], "-i asks the NRL parts"),
    ],
)
def test_response_file_parts_follow_the_rules_before_any_table(
    cache_root, fake_service, options, message
):
    result = runner.invoke(
        app,
        [
            "response",
            "--sensor-file",
            str(DATA_DIR / "nrl_part_sts2.xml"),
            *options,
            "--cache-root",
            str(cache_root),
        ],
        terminal_width=300,
    )

    assert result.exit_code == 1
    assert message in result.output
    assert "configuration" not in result.output
    assert fake_service.requests == []


def test_response_unreadable_file(cache_root, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("not a response")
    arguments = ["response", "--datalogger", "Q330", "--cache-root", str(cache_root)]

    unknown = runner.invoke(app, [*arguments, "--sensor-file", str(notes)])
    missing = runner.invoke(app, [*arguments, "--sensor-file", str(tmp_path / "x")])

    assert unknown.exit_code == 1
    assert "Unknown format" in " ".join(unknown.output.split())
    assert missing.exit_code == 1
    assert "No such file" in missing.output


def test_response_checks_the_labels_before_any_table(cache_root, fake_service):
    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "--channels",
            "HHZ,HHZ",
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 1
    assert "The channels must be unique" in result.output
    assert "configuration" not in result.output


def test_response_writes_sacpz(cache_root, fake_service, make_stationxml, tmp_path):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    output = tmp_path / "st.pz"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "-o",
            str(output),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 0, result.output
    text = output.read_text()
    assert "* CHANNEL     : ZZZ" in text
    assert "CONSTANT" in text
