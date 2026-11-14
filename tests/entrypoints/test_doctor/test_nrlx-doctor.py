from __future__ import annotations

from typer.testing import CliRunner

from nrlx.tools.cmd import app

runner = CliRunner()


def test_doctor_good_stationxml(valid_response_xml):
    result = runner.invoke(app, ["doctor", str(valid_response_xml)])

    assert result.exit_code == 0
    assert "Contains a Response element." in result.output


def test_doctor_good_resp(valid_response_resp):
    result = runner.invoke(app, ["doctor", str(valid_response_resp)])

    assert result.exit_code == 0


def test_doctor_format_flag_overrides_the_extension(tmp_path, valid_response_xml):
    path = tmp_path / "response.dat"
    path.write_bytes(valid_response_xml.read_bytes())

    result = runner.invoke(app, ["doctor", str(path), "--format", "stationxml"])

    assert result.exit_code == 0


def test_doctor_unknown_extension(tmp_path):
    path = tmp_path / "response.dat"
    path.write_bytes(b"data")

    result = runner.invoke(app, ["doctor", str(path)])

    assert result.exit_code == 1
    assert "Cannot infer response format" in result.output


def test_doctor_missing_file(tmp_path):
    result = runner.invoke(app, ["doctor", str(tmp_path / "missing.xml")])

    assert result.exit_code == 1
    assert "missing.xml" in result.output


def test_doctor_html_saved_as_xml(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(b"<html><body>404</body></html>")

    result = runner.invoke(app, ["doctor", str(path)])

    assert result.exit_code == 1
    assert "No Response element found." in result.output


def test_doctor_refuses_sacpz(tmp_path):
    path = tmp_path / "station.pz"
    path.write_text("ZEROS 0\nPOLES 0\nCONSTANT 1.0\n")

    result = runner.invoke(app, ["doctor", str(path), "--format", "sacpz"])

    assert result.exit_code == 1
    assert "nrlx doctor does not check SACPZ files yet." in result.output
