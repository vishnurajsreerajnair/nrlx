from __future__ import annotations

import warnings
from pathlib import Path

import obspy
from typer.testing import CliRunner

from nrlx.models.nrlx import Nrlx
from nrlx.tools.cmd import app

runner = CliRunner()

DATA_DIR = Path(__file__).parents[2] / "data"

SENSOR = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
DATALOGGER = "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def doctor(args: list[str]) -> tuple[int, str]:
    """Exit code and output of nrlx doctor"""
    result = runner.invoke(app, ["doctor", *args], terminal_width=200)

    return result.exit_code, result.output


def built_by_nrlx(cache_root: Path, fake_service, path: Path) -> Path:
    """StationXML of XY.T13.00.HHZ, HHN and HHE built by nrlx from the service,
    STS-2 and Q330, with its provenance comment"""
    fake_service.contents["combine"] = (DATA_DIR / "nrl_sts2_q330.xml").read_bytes()
    nrl = Nrlx.from_cache(cache_root)
    inventory, _ = nrl.response(
        sensor=["STS-2", "SG=1500"],
        datalogger=["Q330"],
        network="XY",
        station="T13",
        location="00",
        channels=["HHZ", "HHN", "HHE"],
    )
    inventory.write(str(path), format="STATIONXML")

    return path


# tier 2


def test_doctor_checks_each_channel(station_xml, tmp_path):
    code, output = doctor([str(station_xml), "--cache-root", str(tmp_path)])

    # the band of a 40 sps channel is B or S: a warning, not an error
    assert code == 0, output
    assert "(3 channels)" in output
    assert output.count("band H for 40 sps: the SEED norm gives B or S") == 3
    assert "stages numbered 1 to 4" not in output


def test_doctor_all_lists_every_check(station_xml, tmp_path):
    code, output = doctor([str(station_xml), "--all", "--no-nominal"])

    assert code == 0, output
    assert "XY.T13.00.HHE chains: stages numbered 1 to 4" in output
    assert "nominal: not compared (--no-nominal)" in output


def test_doctor_checks_one_channel(station_xml):
    code, output = doctor([f"{station_xml}#XY.T13.00.HHE", "--no-nominal"])

    assert code == 0, output
    assert "(1 channel)" in output
    assert "XY.T13.00.HHZ" not in output


def test_doctor_unknown_channel_lists_the_channels(station_xml):
    code, output = doctor([f"{station_xml}#XY.T13.00.BHZ", "--no-nominal"])

    assert code == 1
    assert "Error: No channel XY.T13.00.BHZ" in output
    assert "XY.T13.00.HHZ" in output


def test_doctor_reads_resp(tmp_path):
    code, output = doctor([str(DATA_DIR / "nrl_sts2_q330.resp"), "--no-nominal"])

    assert code == 0, output
    assert "XX.YY.00.ZZZ" in output


def test_doctor_fails_on_a_pole_of_the_wrong_sign(tmp_path):
    # the poles of the STS-2 written with a positive real part
    inventory = obspy.read_inventory(DATA_DIR / "nrl_sts2_q330.xml")
    stage = inventory[0][0][0].response.response_stages[0]
    stage.poles = [complex(-pole.real, pole.imag) for pole in stage.poles]
    path = tmp_path / "flipped.xml"
    inventory.write(str(path), format="STATIONXML")

    code, output = doctor([str(path), "--no-nominal"])

    assert code == 1
    assert "1 error" in output
    assert "poles: stage 1: unstable poles" in output


def test_doctor_checks_sacpz_with_its_rate(station_xml, tmp_path):
    path = tmp_path / "station.pz"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        obspy.read_inventory(str(station_xml)).write(str(path), format="SACPZ")

    code, output = doctor([str(path), "--all"])

    assert code == 0, output
    assert "XY.T13.00.HHZ poles: CONSTANT" in output
    assert "band H for 40 sps" in output
    assert "SACPZ has no stages" in output


def test_doctor_shows_why_obspy_cannot_read_a_file(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(b"<html><body>404</body></html>")

    code, output = doctor([str(path)])

    assert code == 1
    assert "obspy cannot read it" in output
    assert "File looks like an HTML error page, not RESP." in output


def test_doctor_missing_file(tmp_path):
    code, output = doctor([str(tmp_path / "missing.xml")])

    assert code == 1
    assert "Error:" in output
    assert "missing.xml" in output


# tier 3


def test_doctor_compares_with_the_nominal_of_the_comment(
    cache_root, fake_service, tmp_path
):
    path = built_by_nrlx(cache_root, fake_service, tmp_path / "built.xml")

    code, output = doctor([str(path), "--cache-root", str(cache_root), "--all"])

    assert code == 0, output
    # the line of the nominal, wrapped by Rich
    assert f"nominal: sensor={SENSOR} datalogger={DATALOGGER} (service)" in " ".join(
        output.split()
    )
    assert output.count("nominal: amplitude within 0% of the nominal") == 3
    # one request for the build, one for the nominal of the three channels
    assert len(fake_service.requests) == 2


def test_doctor_warns_on_a_calibrated_gain_with_the_stage(
    cache_root, fake_service, tmp_path
):
    path = built_by_nrlx(cache_root, fake_service, tmp_path / "built.xml")
    inventory = obspy.read_inventory(str(path))
    for channel in inventory[0][0]:
        channel.response.response_stages[0].stage_gain *= 1.02
        channel.response.instrument_sensitivity.value *= 1.02
    inventory.write(str(path), format="STATIONXML")

    code, output = doctor([str(path), "--cache-root", str(cache_root)])

    assert code == 0, output
    assert "XY.T13.00.HHZ nominal: amplitude +2% from the nominal" in output
    assert "XY.T13.00.HHZ nominal: differs: stage 1: gain 1530 for 1500" in output


def test_doctor_takes_the_keys_for_a_file_without_comment(
    cache_root, fake_service, station_xml
):
    fake_service.contents["combine"] = (DATA_DIR / "nrl_sts2_q330.xml").read_bytes()

    code, output = doctor(
        [
            str(station_xml),
            "--cache-root",
            str(cache_root),
            "--sensor",
            "STS-2,SG=1500",
            "--datalogger",
            "Q330",
        ]
    )

    assert code == 0, output
    assert "nominal: sensor=STS-2 SG=1500 datalogger=Q330 (service)" in output
    assert len(fake_service.requests) == 1


def test_doctor_without_parts_does_not_compare(cache_root, fake_service, station_xml):
    code, output = doctor([str(station_xml), "--cache-root", str(cache_root), "--all"])

    assert code == 0, output
    assert "not compared: no NRL parts" in output
    assert fake_service.requests == []


def test_doctor_keys_without_a_catalog_are_an_error(station_xml, tmp_path):
    code, output = doctor(
        [str(station_xml), "--cache-root", str(tmp_path), "--sensor", "STS-2"]
    )

    assert code == 1
    assert "Error:" in output


def test_doctor_goes_on_when_the_service_fails(cache_root, fake_service, tmp_path):
    path = built_by_nrlx(cache_root, fake_service, tmp_path / "built.xml")
    fake_service.status_code = 500

    code, output = doctor([str(path), "--cache-root", str(cache_root), "--all"])

    assert code == 0, output
    assert "not compared: NRL service request failed" in output


def test_doctor_no_nominal_sends_no_request(cache_root, fake_service, tmp_path):
    path = built_by_nrlx(cache_root, fake_service, tmp_path / "built.xml")

    code, _ = doctor([str(path), "--cache-root", str(cache_root), "--no-nominal"])

    assert code == 0
    assert len(fake_service.requests) == 1
