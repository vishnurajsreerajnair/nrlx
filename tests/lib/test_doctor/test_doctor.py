from __future__ import annotations

from pathlib import Path

import pytest

from nrlx.core.doctor import check_response, infer_format


def test_infer_format_from_extension():
    assert infer_format(Path("a.xml")) == "stationxml"
    assert infer_format(Path("a.RESP")) == "resp"


def test_infer_format_unknown_extension_raises():
    with pytest.raises(ValueError, match="Cannot infer response format"):
        infer_format(Path("a.dat"))


def test_valid_stationxml_has_no_errors(valid_response_xml):
    findings = check_response(valid_response_xml.read_bytes(), "stationxml")

    assert all(severity == "ok" for severity, _ in findings)
    assert ("ok", "Contains a Response element.") in findings


def test_invalid_xml_is_an_error():
    [(severity, message)] = check_response(b"<not><valid xml", "stationxml")

    assert severity == "error"
    assert message.startswith("Not valid XML")


def test_html_error_page_saved_as_xml_is_an_error():
    findings = check_response(b"<html><body>404 Not Found</body></html>", "stationxml")

    assert ("error", "No Response element found.") in findings


def test_xml_without_codes_is_a_warning():
    findings = check_response(
        b"<FDSNStationXML><Response/></FDSNStationXML>", "stationxml"
    )

    assert ("ok", "Contains a Response element.") in findings
    assert ("warning", "No Network element found.") in findings


def test_valid_resp_has_no_errors(valid_response_resp):
    findings = check_response(valid_response_resp.read_bytes(), "resp")

    assert findings == [
        ("ok", "Contains RESP blockette lines."),
        ("ok", "Contains a response stage or gain blockette."),
    ]


@pytest.mark.parametrize("format", ["resp", "stationxml"])
def test_empty_file_is_an_error(format):
    assert check_response(b"  \n", format) == [("error", "File is empty.")]


def test_resp_without_blockettes_is_an_error():
    findings = check_response(b"not a resp file at all", "resp")

    assert ("error", "No RESP blockette lines (e.g. B052F03) found.") in findings


def test_resp_html_error_page_is_an_error():
    assert check_response(b"<html><body>Error</body></html>", "resp") == [
        ("error", "File looks like an HTML error page, not RESP.")
    ]


def test_resp_without_gain_blockette_is_a_warning():
    findings = check_response(b"B050F03     Station:     YY\n", "resp")

    assert [severity for severity, _ in findings] == ["ok", "warning"]
