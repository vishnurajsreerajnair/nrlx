"""Structural health checks for saved response files.

Offline, dependency-light checks (no obspy, no network): is the file well-formed
RESP/XML with the pieces a response should have.


"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from xml.etree import ElementTree

from nrlx.exceptions import NrlxResponseError
from nrlx.formats import ResponseFormat

# Tier 1 of 3: structural checks only, no obspy dependency. Metadata-sanity and
# physical-response-sanity checks (tiers 2-3) are deferred to nrlx.response.
_BLOCKETTE_LINE = re.compile(r"^B\d{3}F\d{2}\b", re.MULTILINE)


class Severity(str, Enum):
    """Severity of a single health check finding."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Finding:
    """A single health check result.

    Args:
        severity: How serious this finding is.
        message: Human-readable description of what was checked.


    """
    severity: Severity
    message: str


@dataclass(frozen=True)
class HealthReport:
    """Structural health check results for a saved response file.

    Args:
        path: Response file that was checked.
        format: Response format the file was checked against.
        findings: All findings from the check, in check order.


    """
    path: Path
    format: ResponseFormat
    findings: tuple[Finding, ...]

    @property
    def ok(self) -> bool:
        """Whether the file passed all checks (no ERROR-severity findings)."""
        return not any(f.severity == Severity.ERROR for f in self.findings)

    @classmethod
    def from_file(
        cls,
        path: Path,
        format: ResponseFormat
    ) -> HealthReport:
        """Run structural health checks on a saved response file.

        These are cheap, offline, structural checks only - do we have well-formed
        RESP/XML with the expected pieces present. They do not evaluate whether the
        response function itself is physically sane;
        that requires parsing and evaluating the response
        (planned for the nrlx.response module).

        Args:
            path: Response file to check.
            format: Response format to check against.

        Returns:
            HealthReport with all findings from the check.

        Raises:
            NrlxResponseError: If the file does not exist.


        """
        if not path.exists():
            raise NrlxResponseError(f"Response file not found: {path}")

        content = path.read_bytes()

        if format == ResponseFormat.RESP:
            findings = cls._check_resp(content)
        else:
            findings = cls._check_xml_response(content)

        return cls(
            path=path,
            format=format,
            findings=findings
        )

    @staticmethod
    def _check_resp(content: bytes) -> tuple[Finding, ...]:
        """Structurally check RESP (SEED blockette) content."""
        if not content.strip():
            return (Finding(Severity.ERROR, "File is empty."),)

        text = content.decode("utf-8", errors="replace")

        if "<html" in text.lower():
            message = "File looks like an HTML error page, not RESP."
            return (Finding(Severity.ERROR, message),)

        findings: list[Finding] = []

        if _BLOCKETTE_LINE.search(text):
            findings.append(Finding(Severity.OK, "Contains RESP blockette lines."))
        else:
            findings.append(
                Finding(Severity.ERROR, "No RESP blockette lines (e.g. B052F03) found.")
            )

        if any(code in text for code in ("B053F", "B058F", "B054F")):
            findings.append(
                Finding(Severity.OK, "Contains a response stage or gain blockette.")
            )
        else:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "No poles/zeros (B053), coefficients (B054), or gain (B058) "
                    "blockette found — response may be incomplete.",
                )
            )

        return tuple(findings)

    @staticmethod
    def _check_xml_response(content: bytes) -> tuple[Finding, ...]:
        """Structurally check StationXML / StationXML-Response content."""
        if not content.strip():
            return (Finding(Severity.ERROR, "File is empty."),)

        try:
            root = ElementTree.fromstring(content)
        except ElementTree.ParseError as exc:
            return (Finding(Severity.ERROR, f"Not valid XML: {exc}"),)

        findings = [Finding(Severity.OK, "Valid XML.")]

        def has_element(tag_suffix: str) -> bool:
            return any(el.tag.endswith(tag_suffix) for el in root.iter())

        if has_element("Response"):
            findings.append(Finding(Severity.OK, "Contains a Response element."))
        else:
            findings.append(Finding(Severity.ERROR, "No Response element found."))

        for tag_suffix in ("Network", "Station", "Channel"):
            if has_element(tag_suffix):
                findings.append(
                    Finding(Severity.OK, f"Contains a {tag_suffix} element.")
                )
            else:
                findings.append(
                    Finding(Severity.WARNING, f"No {tag_suffix} element found.")
                )

        return tuple(findings)


def infer_format(path: Path) -> ResponseFormat:
    """Infer a response format from a file's extension.

    Args:
        path: Response file path.

    Returns:
        Inferred response format.

    Raises:
        NrlxResponseError: If the format cannot be inferred from the extension.


    """
    suffix = path.suffix.lower()

    if suffix == ".resp":
        return ResponseFormat.RESP
    if suffix == ".xml":
        return ResponseFormat.STATIONXML

    raise NrlxResponseError(
        f"Cannot infer response format from extension {suffix!r}. "
        "Pass --format explicitly."
    )
