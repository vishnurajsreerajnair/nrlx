"""End-to-end battery of nrlx response through the command: the sources, the
formats by extension, the parts from files, --split, the errors, and nrlx doctor
on every file written

Reads battery.json of build_battery.py, for a pair (its local build is the
reference of the curves) and an integrated instrument. A few requests go to the
service, spaced by --pause seconds. Writes cli.json.

Example:

    python scripts/e2e/cli_battery.py --cache-root CACHE --out OUT


"""

from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import msgspec
import obspy
from common import curve, deviation, grid, run_nrlx

from nrlx.io.resp import write_resp

# the pair of battery.json the cases build
PAIR = 13


class CliCase(msgspec.Struct, frozen=True, kw_only=True):
    """A run of nrlx response

    Args:
        name: what it checks.
        command: the command, with the paths shortened.
        exit: its exit code.
        expected: the exit code expected.
        tail: the last lines of its output.


    """

    name: str
    command: str
    exit: int
    expected: int
    tail: str


class DoctorRun(msgspec.Struct, frozen=True, kw_only=True):
    """A run of nrlx doctor on a file written

    Args:
        file: name of the file.
        exit: exit code.
        summary: the first line telling ok, a warning or an error.


    """

    file: str
    exit: int
    summary: str


class Labels(msgspec.Struct, frozen=True, kw_only=True):
    """The labels of the first file, as obspy reads them

    Args:
        network: network code.
        station: station code.
        channels: channel codes.
        latitude: latitude of the first channel.
        start: start date of the first channel.


    """

    network: str
    station: str
    channels: list[str]
    latitude: float
    start: str


class CliResult(msgspec.Struct, frozen=True, kw_only=True):
    """The result of the battery, cli.json

    Args:
        cases: the runs of nrlx response.
        checks: curve of each file written against the local build of the pair.
        labels: the labels of the first file.
        split: the files of --split.
        doctor: the runs of nrlx doctor.


    """

    cases: list[CliCase]
    checks: dict[str, float]
    labels: Labels
    split: list[str]
    doctor: list[DoctorRun]


class PairInput(msgspec.Struct, frozen=True):
    """A pair of battery.json, its parts only

    Args:
        sensor: instconfig of the sensor.
        datalogger: instconfig of the datalogger.


    """

    sensor: str
    datalogger: str


class SingleInput(msgspec.Struct, frozen=True):
    """A single part of battery.json, its element and instconfig only

    Args:
        element: sensor, datalogger, integrated or soh.
        instconfig: instconfig of the part.


    """

    element: str
    instconfig: str


class BatteryInput(msgspec.Struct, frozen=True):
    """battery.json, the parts only

    Args:
        pairs: the pairs.
        singles: the single parts.


    """

    pairs: list[PairInput]
    singles: list[SingleInput]


def first_curve_difference(reference: Path, path: Path) -> float:
    """Curve of the first channel of a file against that of a reference file

    Args:
        reference: the reference file.
        path: the file compared.

    Returns:
        the largest relative difference.


    """
    channel = obspy.read_inventory(str(reference))[0][0][0]
    frequencies = grid(channel.sample_rate)
    other = obspy.read_inventory(str(path))[0][0][0].response
    difference = deviation(
        curve(channel.response, frequencies), curve(other, frequencies)
    )

    return difference


def main() -> None:
    """Run the battery: the arguments, the cases, cli.json in the output folder
    and a line per case on the standard output


    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--pause", type=float, default=0.3)
    arguments = parser.parse_args()
    warnings.simplefilter("ignore")
    out, cache = arguments.out, arguments.cache_root
    battery = msgspec.json.decode(
        (out / "battery.json").read_bytes(), type=BatteryInput
    )
    sensor, datalogger = battery.pairs[PAIR].sensor, battery.pairs[PAIR].datalogger
    integrated = next(
        single.instconfig
        for single in battery.singles
        if single.element == "integrated"
    )
    cli = out / "cli"
    cli.mkdir(exist_ok=True)

    # the sensor alone as RESP, and the local build of the pair as the datalogger
    element, manufacturer, rest = sensor.split("_", 2)
    sensor_xml = cache / "nrl" / "NRL" / element / manufacturer / f"{rest}.xml"
    sensor_resp = cli / "sensor_alone.resp"
    sensor_resp.write_text(write_resp(obspy.read_inventory(str(sensor_xml))))
    reference = out / "pairs" / f"{PAIR:02d}" / "local.xml"
    channels = ["--channels", "HHZ,HHN,HHE"]
    labels = ["--network", "XY", "--station", "T13", "--location", "00", *channels]
    parts = ["--sensor", sensor, "--datalogger", datalogger]
    local = ["--source", "local"]

    # name, arguments of nrlx response and the exit code expected
    cases = [
        (
            "service, StationXML, labels and place",
            [
                *parts,
                *labels,
                "--starttime",
                "2026-01-01",
                "--latitude",
                "45.6",
                "--longitude",
                "8.9",
                "-o",
                str(cli / "01_service.xml"),
            ],
            0,
        ),
        (
            "local, RESP",
            [*parts, *labels, *local, "-o", str(cli / "02_local.resp")],
            0,
        ),
        (
            "local, --split StationXML",
            [*parts, *labels, *local, "--split", "-o", str(cli / "03_split.xml")],
            0,
        ),
        (
            "--format resp on a .txt",
            [*parts, *local, "--format", "resp", "-o", str(cli / "04_format.txt")],
            0,
        ),
        (
            "--sensor-file .resp + datalogger from the service",
            [
                "--sensor-file",
                str(sensor_resp),
                "--datalogger",
                datalogger,
                "-o",
                str(cli / "05_sensorfile.xml"),
            ],
            0,
        ),
        (
            "--datalogger-file whole channel #id + sensor local",
            [
                "--sensor",
                sensor,
                "--datalogger-file",
                f"{reference}#XX.YY.00.ZZZ",
                *local,
                "-o",
                str(cli / "06_dlfile.resp"),
            ],
            0,
        ),
        (
            "two files, no service",
            [
                "--sensor-file",
                str(sensor_xml),
                "--datalogger-file",
                str(reference),
                "-o",
                str(cli / "07_files.xml"),
            ],
            0,
        ),
        (
            "integrated, local",
            ["--integrated", integrated, *local, "-o", str(cli / "08_integrated.xml")],
            0,
        ),
        (
            "explore: file + partial datalogger keys",
            [
                "--sensor-file",
                str(sensor_xml),
                "--datalogger",
                "GaiaCode,TAU-Mk2,FR=100",
            ],
            0,
        ),
        (
            "error: unknown extension",
            [*parts, *local, "-o", str(cli / "09.json")],
            1,
        ),
        (
            "error: a file alone",
            ["--sensor-file", str(sensor_xml), "-o", str(cli / "10.xml")],
            1,
        ),
        (
            "error: keys and a file for the sensor",
            [*parts, "--sensor-file", str(sensor_xml)],
            1,
        ),
        ("error: -i with a file", ["-i", "--sensor-file", str(sensor_xml)], 1),
    ]
    results = list()
    for name, case_arguments, expected in cases:
        time.sleep(arguments.pause)
        code, output = run_nrlx(
            ["response", *case_arguments, "--cache-root", str(cache)]
        )
        shown = " ".join(
            argument.replace(f"{out}/", "").replace(str(cache), "cache")
            for argument in case_arguments
        )
        results.append(
            CliCase(
                name=name,
                command=f"nrlx response {shown}",
                exit=code,
                expected=expected,
                tail="\n".join(output.strip().splitlines()[-4:]),
            )
        )
        print(code == expected, name, code, flush=True)

    # the curve of each file written against the local build of the pair
    written = {
        "01 service vs local pair": cli / "01_service.xml",
        "02 RESP vs local pair": cli / "02_local.resp",
        "03 split HHE vs local pair": cli / "03_split_XY.T13.00.HHE.xml",
        "04 .txt RESP vs local pair": cli / "04_format.txt",
        "05 sensor-file RESP vs local pair": cli / "05_sensorfile.xml",
        "06 datalogger-file vs local pair": cli / "06_dlfile.resp",
        "07 two files vs local pair": cli / "07_files.xml",
    }
    checks = {
        name: first_curve_difference(reference, path) for name, path in written.items()
    }
    first = obspy.read_inventory(str(cli / "01_service.xml"))[0]
    found = Labels(
        network=first.code,
        station=first[0].code,
        channels=[channel.code for channel in first[0]],
        latitude=float(first[0][0].latitude),
        start=str(first[0][0].start_date),
    )
    split = sorted(path.name for path in cli.glob("03_split_*"))

    # nrlx doctor on every file written
    doctor = list()
    for path in sorted(cli.glob("0*")):
        code, output = run_nrlx(["doctor", str(path), "--cache-root", str(cache)])
        lines = output.strip().splitlines()
        summary = next(
            (
                line
                for line in lines
                if any(word in line.lower() for word in ("ok", "warning", "error"))
            ),
            lines[-1] if lines else "",
        )
        doctor.append(DoctorRun(file=path.name, exit=code, summary=summary))
        print("doctor", path.name, code, flush=True)

    result = CliResult(
        cases=results, checks=checks, labels=found, split=split, doctor=doctor
    )
    (out / "cli.json").write_bytes(
        msgspec.json.format(msgspec.json.encode(result), indent=1)
    )
    for name, difference in checks.items():
        print(f"{name}: {difference:.1e}")
    passed = sum(case.exit == case.expected for case in results)
    print(f"{passed} of {len(results)} exit codes as expected; split {split}")


if __name__ == "__main__":
    main()
