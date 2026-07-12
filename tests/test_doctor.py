from __future__ import annotations

import subprocess
import sys

import pytest

from nrlx.doctor import Finding, HealthReport, Severity, infer_format
from nrlx.exceptions import NrlxResponseError
from nrlx.formats import ResponseFormat


def test_importing_doctor_does_not_load_the_network_stack():
    # Fresh interpreter: in-process sys.modules is already polluted by other
    # tests. The offline doctor must stay importable without httpx.
    code = "import sys, nrlx.doctor; assert 'httpx' not in sys.modules"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True)

    assert result.returncode == 0, result.stderr.decode()

_VALID_STATIONXML = b"""<?xml version="1.0"?>
<FDSNStationXML xmlns="http://www.fdsn.org/xml/station/1">
  <Network code="XX">
    <Station code="YY">
      <Channel code="ZZZ" locationCode="00">
        <Response>
          <InstrumentSensitivity><Value>1.0</Value></InstrumentSensitivity>
        </Response>
      </Channel>
    </Station>
  </Network>
</FDSNStationXML>
"""

_VALID_RESP = """#
###
B050F03     Station:     YY
B052F03     Location:    00
B052F04     Channel:     ZZZ
B053F03     Transfer function type:                A
B058F04     Sensitivity:                            1.0
"""


def test_infer_format_from_extension(tmp_path):
    assert infer_format(tmp_path / "a.xml") == ResponseFormat.STATIONXML
    assert infer_format(tmp_path / "a.resp") == ResponseFormat.RESP


def test_infer_format_unknown_extension_raises(tmp_path):
    with pytest.raises(NrlxResponseError, match="Cannot infer response format"):
        infer_format(tmp_path / "a.dat")


def test_from_file_missing_file_raises(tmp_path):
    with pytest.raises(NrlxResponseError, match="Response file not found"):
        HealthReport.from_file(tmp_path / "missing.xml", ResponseFormat.STATIONXML)


def test_valid_stationxml_has_no_errors(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(_VALID_STATIONXML)

    report = HealthReport.from_file(path, ResponseFormat.STATIONXML)

    assert report.ok
    assert any(f.message == "Contains a Response element." for f in report.findings)


def test_invalid_xml_is_an_error(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(b"<not><valid xml")

    report = HealthReport.from_file(path, ResponseFormat.STATIONXML)

    assert not report.ok
    assert any(f.severity == Severity.ERROR for f in report.findings)


def test_html_error_page_saved_as_xml_is_an_error(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(b"<html><body>404 Not Found</body></html>")

    report = HealthReport.from_file(path, ResponseFormat.STATIONXML)

    assert not report.ok


def test_xml_missing_response_element_is_an_error(tmp_path):
    path = tmp_path / "response.xml"
    path.write_bytes(b"<FDSNStationXML><Network code='XX'/></FDSNStationXML>")

    report = HealthReport.from_file(path, ResponseFormat.STATIONXML)

    assert not report.ok
    assert any(f.message == "No Response element found." for f in report.findings)


def test_valid_resp_has_no_errors(tmp_path):
    path = tmp_path / "response.resp"
    path.write_text(_VALID_RESP, encoding="utf-8")

    report = HealthReport.from_file(path, ResponseFormat.RESP)

    assert report.ok


def test_empty_file_is_an_error(tmp_path):
    path = tmp_path / "response.resp"
    path.write_text("", encoding="utf-8")

    report = HealthReport.from_file(path, ResponseFormat.RESP)

    assert not report.ok
    assert report.findings == (Finding(Severity.ERROR, "File is empty."),)


def test_resp_without_blockettes_is_an_error(tmp_path):
    path = tmp_path / "response.resp"
    path.write_text("not a resp file at all", encoding="utf-8")

    report = HealthReport.from_file(path, ResponseFormat.RESP)

    assert not report.ok


def test_resp_html_error_page_is_an_error(tmp_path):
    path = tmp_path / "response.resp"
    path.write_text("<html><body>Error</body></html>", encoding="utf-8")

    report = HealthReport.from_file(path, ResponseFormat.RESP)

    assert not report.ok


def test_resp_without_gain_blockette_is_a_warning(tmp_path):
    path = tmp_path / "response.resp"
    path.write_text("B050F03     Station:     YY\n", encoding="utf-8")

    report = HealthReport.from_file(path, ResponseFormat.RESP)

    assert report.ok
    assert any(f.severity == Severity.WARNING for f in report.findings)
