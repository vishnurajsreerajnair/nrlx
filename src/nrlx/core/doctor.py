"""Structural health checks of the response files

Tier 1 of 3: offline structural checks, whether the content is well-formed RESP or
XML with the parts of a response. Whether the response is physically sane needs to
evaluate it, and is not checked yet.


"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from nrlx.schema.response import ResponseFormat

Severity = Literal["ok", "warning", "error"]

# a line of a RESP blockette, for example B052F03
BLOCKETTE_LINE = re.compile(r"^B\d{3}F\d{2}\b", re.MULTILINE)


def infer_format(path: Path) -> ResponseFormat:
    """Format of a response file from its extension, .resp or .xml

    Args:
        path: response file.

    Returns:
        format of the response.

    Raises:
        ValueError: if the extension is not .resp or .xml.


    """
    match path.suffix.lower():
        case ".resp":
            responseformat: ResponseFormat = "resp"
        case ".xml":
            responseformat = "stationxml"
        case suffix:
            raise ValueError(
                f"Cannot infer response format from extension {suffix!r}. "
                "Pass --format explicitly."
            )

    return responseformat


def check_response(
    content: bytes, format: ResponseFormat
) -> list[tuple[Severity, str]]:
    """Structural checks of a response, in the RESP or XML format

    Args:
        content: content of the response file.
        format: format of the response.

    Returns:
        severity and message of each check, in check order.

    Raises:
        ValueError: for a SACPZ file, which doctor does not check yet.


    """
    match format:
        case "resp":
            findings = check_resp(content)
        case "stationxml":
            findings = check_stationxml(content)
        case "sacpz":
            raise ValueError("nrlx doctor does not check SACPZ files yet.")

    return findings


def check_resp(content: bytes) -> list[tuple[Severity, str]]:
    """Structural checks of a RESP response: SEED blockette lines and a stage

    Args:
        content: content of the RESP file.

    Returns:
        severity and message of each check, in check order.


    """
    text = content.decode("utf-8", errors="replace")

    # an empty file or an html error page saved as RESP stop the checks
    findings: list[tuple[Severity, str]] = list()
    if not text.strip():
        findings.append(("error", "File is empty."))
    elif "<html" in text.lower():
        findings.append(("error", "File looks like an HTML error page, not RESP."))
    else:
        # the blockette lines make a RESP file
        if BLOCKETTE_LINE.search(text):
            findings.append(("ok", "Contains RESP blockette lines."))
        else:
            findings.append(("error", "No RESP blockette lines (e.g. B052F03) found."))

        # a response needs a stage or a gain
        if any(code in text for code in ["B053F", "B058F", "B054F"]):
            findings.append(("ok", "Contains a response stage or gain blockette."))
        else:
            findings.append(
                (
                    "warning",
                    "No poles/zeros (B053), coefficients (B054), or gain (B058) "
                    "blockette found — response may be incomplete.",
                )
            )

    return findings


def check_stationxml(content: bytes) -> list[tuple[Severity, str]]:
    """Structural checks of a StationXML response: valid XML, response and codes

    Args:
        content: content of the StationXML file.

    Returns:
        severity and message of each check, in check order.


    """
    # an empty file or an invalid xml stop the checks
    findings: list[tuple[Severity, str]] = list()
    if not content.strip():
        findings.append(("error", "File is empty."))
    else:
        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as err:
            findings.append(("error", f"Not valid XML: {err}"))
        else:
            findings.append(("ok", "Valid XML."))

            # the tags end with the element names, after the namespace
            tags = [element.tag for element in root.iter()]

            # the response is needed
            if any(tag.endswith("Response") for tag in tags):
                findings.append(("ok", "Contains a Response element."))
            else:
                findings.append(("error", "No Response element found."))

            # the codes are expected
            for name in ["Network", "Station", "Channel"]:
                if any(tag.endswith(name) for tag in tags):
                    findings.append(("ok", f"Contains a {name} element."))
                else:
                    findings.append(("warning", f"No {name} element found."))

    return findings
