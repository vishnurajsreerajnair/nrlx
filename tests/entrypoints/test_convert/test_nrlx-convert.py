from __future__ import annotations

from pathlib import Path

import obspy
from obspy import Inventory
from typer.testing import CliRunner

from nrlx.io.resp import write_resp
from nrlx.tools.cmd import app

runner = CliRunner()

DATA_DIR = Path(__file__).parents[2] / "data"


def test_convert_stationxml_to_resp(station_xml, tmp_path):
    output = tmp_path / "station.resp"

    result = runner.invoke(app, ["convert", str(station_xml), "-o", str(output)])

    assert result.exit_code == 0, result.output
    assert "Converted to resp, read back and checked" in result.output
    # obspy reads each channel of RESP in a station of its own
    [network] = obspy.read_inventory(str(output))
    assert [cha.code for sta in network for cha in sta] == ["HHZ", "HHN", "HHE"]


def test_convert_dataless_seed_to_stationxml(dataless_seed, tmp_path):
    output = tmp_path / "station.xml"

    result = runner.invoke(app, ["convert", str(dataless_seed), "-o", str(output)])

    assert result.exit_code == 0, result.output
    assert len(obspy.read_inventory(str(output))[0][0][0].response.response_stages) == 4


def test_convert_picks_one_channel(station_xml, tmp_path):
    output = tmp_path / "one.xml"

    result = runner.invoke(
        app, ["convert", f"{station_xml}#XY.T13.00.HHE", "-o", str(output)]
    )

    assert result.exit_code == 0, result.output
    assert [cha.code for cha in obspy.read_inventory(str(output))[0][0]] == ["HHE"]


def test_convert_unknown_channel_lists_the_channels(station_xml, tmp_path):
    result = runner.invoke(
        app,
        ["convert", f"{station_xml}#XY.T13.00.BHZ", "-o", str(tmp_path / "a.xml")],
        terminal_width=200,
    )

    assert result.exit_code == 1
    assert "Error: No channel XY.T13.00.BHZ" in result.output
    assert "XY.T13.00.HHZ" in result.output


def test_convert_split_writes_one_sacpz_per_channel_with_the_notes(
    station_xml, tmp_path
):
    result = runner.invoke(
        app,
        ["convert", str(station_xml), "-o", str(tmp_path / "st.pz"), "--split"],
        terminal_width=200,
    )

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in tmp_path.glob("st_*")) == [
        "st_XY.T13.00.HHE.pz",
        "st_XY.T13.00.HHN.pz",
        "st_XY.T13.00.HHZ.pz",
    ]
    assert result.output.count("drops the other 3 stages") == 3


def test_convert_format_overrides_the_extension(station_xml, tmp_path):
    output = tmp_path / "station.txt"

    result = runner.invoke(
        app, ["convert", str(station_xml), "-o", str(output), "--format", "resp"]
    )

    assert result.exit_code == 0, result.output
    assert output.read_text().startswith("#")


def test_convert_unknown_extension_writes_nothing(station_xml, tmp_path):
    output = tmp_path / "station.txt"

    result = runner.invoke(app, ["convert", str(station_xml), "-o", str(output)])

    assert result.exit_code == 1
    assert "Cannot tell the format from .txt" in result.output
    assert not output.exists()


def test_convert_missing_file(tmp_path):
    result = runner.invoke(
        app,
        ["convert", str(tmp_path / "none.xml"), "-o", str(tmp_path / "a.resp")],
    )

    assert result.exit_code == 1
    assert "Error:" in result.output


def test_convert_refuses_sacpz_without_poles_and_zeros(tmp_path):
    output = tmp_path / "poly.pz"

    result = runner.invoke(
        app,
        ["convert", str(DATA_DIR / "nrl_poly.xml"), "-o", str(output)],
        terminal_width=200,
    )

    assert result.exit_code == 1
    assert "SACPZ holds only the channels with analog poles and zeros" in result.output
    assert not output.exists()


def test_convert_fails_when_the_file_reads_back_different(
    station_xml, tmp_path, monkeypatch
):
    # a writer that rounds the gain of the sensor
    def rounding_writer(inventory: Inventory) -> str:
        return write_resp(inventory).replace(
            "+1.500000000000000E+03", "+1.501000000000000E+03"
        )

    monkeypatch.setattr("nrlx.io.inventory.write_resp", rounding_writer)
    output = tmp_path / "station.resp"

    result = runner.invoke(
        app,
        ["convert", str(station_xml), "-o", str(output)],
        terminal_width=200,
    )

    assert result.exit_code == 1
    assert "reads back 6.7e-04 different from what was written" in result.output
    # the file is kept, to look at
    assert output.exists()
