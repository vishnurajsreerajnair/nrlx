"""Scan every file of the local NRL copy with the physical checks of nrlx doctor

Each sensor, datalogger and integrated file is checked alone, without a sample
rate: its amplitude, its chains of units and rates, its poles and zeros. Writes
scan.json, every warning and error with its file, and prints the count of each
kind of finding, by manufacturer. No request to the service.

Example:

    python scripts/e2e/scan_nrl.py --cache-root CACHE --out OUT


"""

from __future__ import annotations

import argparse
import warnings
from collections import Counter
from pathlib import Path

import msgspec
import obspy
from common import CASE_ERRORS

from nrlx.core.doctor import check_amplitude, check_chains, check_poles

# the elements of the NRL scanned, the folders of its tree
ELEMENTS = ["sensor", "datalogger", "integrated"]


class ScanFinding(msgspec.Struct, frozen=True, kw_only=True):
    """A warning or an error of a file of the NRL

    Args:
        file: path of the file in the tree, element/manufacturer/...
        kind: unstable poles, cancelling pairs, rates break, units break, FIR sum,
            or the group of the check for any other finding.
        severity: warning or error.
        message: the message of nrlx doctor.


    """

    file: str
    kind: str
    severity: str
    message: str


class Scan(msgspec.Struct, kw_only=True):
    """The result of a scan

    Args:
        files: number of files read, by element.
        unreadable: files obspy cannot read, with the error.
        findings: the warnings and errors.


    """

    files: dict[str, int]
    unreadable: list[tuple[str, str]]
    findings: list[ScanFinding]


def finding_kind(group: str, message: str) -> str:
    """Kind of a finding, from its group and its message

    Args:
        group: amplitude, chains or poles.
        message: the message of nrlx doctor.

    Returns:
        the kind, the group itself for a finding of no listed kind.


    """
    match group:
        case "poles" if "unstable poles" in message:
            kind = "unstable poles"
        case "poles" if "zeros cancel" in message:
            kind = "cancelling pairs"
        case "chains" if message.startswith("rates break"):
            kind = "rates break"
        case "chains" if message.startswith("units break"):
            kind = "units break"
        case "amplitude" if "FIR coefficients" in message:
            kind = "FIR sum"
        case _:
            kind = group

    return kind


def main() -> None:
    """Scan the tree: the arguments, scan.json in the output folder and the counts
    on the standard output


    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    arguments = parser.parse_args()
    warnings.simplefilter("ignore")
    tree = arguments.cache_root / "nrl" / "NRL"
    arguments.out.mkdir(parents=True, exist_ok=True)

    # each file alone, with the checks that need no sample rate
    scan = Scan(files=dict(), unreadable=list(), findings=list())
    for element in ELEMENTS:
        for path in sorted((tree / element).rglob("*.xml")):
            name = path.relative_to(tree).as_posix()
            try:
                response = obspy.read_inventory(str(path))[0][0][0].response
            except CASE_ERRORS as err:
                scan.unreadable.append((name, f"{type(err).__name__}: {err}"))
                continue
            scan.files[element] = scan.files.get(element, 0) + 1
            groups = [
                ("amplitude", check_amplitude(response, None)),
                ("chains", check_chains(response, None)),
                ("poles", check_poles(response)),
            ]
            scan.findings += [
                ScanFinding(
                    file=name,
                    kind=finding_kind(group, message),
                    severity=severity,
                    message=message,
                )
                for group, findings in groups
                for severity, message in findings
                if severity in ("warning", "error")
            ]
    (arguments.out / "scan.json").write_bytes(
        msgspec.json.format(msgspec.json.encode(scan), indent=1)
    )

    # the files of each kind, by manufacturer
    print(f"files {scan.files}, unreadable {len(scan.unreadable)}")
    kinds = sorted({finding.kind for finding in scan.findings})
    for kind in kinds:
        files = {finding.file for finding in scan.findings if finding.kind == kind}
        manufacturers = Counter(file.split("/")[1] for file in files)
        listed = ", ".join(
            f"{name} {count}" for name, count in manufacturers.most_common()
        )
        print(f"{kind}: {len(files)} files: {listed}")


if __name__ == "__main__":
    main()
