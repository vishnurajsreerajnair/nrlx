"""End-to-end battery of nrlx convert on random NRL parts, from the local copy

Each route is checked by obspy, independently of the read-back check of nrlx:
StationXML -> RESP -> StationXML (the merged RESP of three channels must come back
as one station), dataless SEED written by obspy from the RESP -> StationXML, and
SACPZ, refused or written, against evalresp and scipy. No request to the service.

Example:

    python scripts/e2e/convert_battery.py --cache-root CACHE --out OUT


"""

from __future__ import annotations

import argparse
import random
import traceback
import warnings
from pathlib import Path

import msgspec
import numpy as np
import obspy
from common import CASE_ERRORS, curve, deviation, grid, run_nrlx
from obspy.core.inventory import Channel
from obspy.io.xseed import Parser
from scipy.signal import freqs_zpk

from nrlx.io.sacpz import read_sacpz
from nrlx.models.nrlx import Nrlx

# SEED 2.4 limits a blockette to 9999 bytes; obspy's writer does not split longer
# ones (a FIR of more than about 415 coefficients), so it corrupts the file
BLOCKETTE_LIMIT = 9999

# the input units SACPZ can hold: displacement, velocity, acceleration
SACPZ_UNITS = ["M", "M/S", "M/SEC", "M/S**2", "M/SEC**2"]


class SacpzCurve(msgspec.Struct, kw_only=True):
    """The curves of a SACPZ file against its channel, for the report

    Args:
        f: frequencies in Hz.
        whole: amplitude of the whole channel in displacement, by evalresp.
        sacpz: amplitude of the poles, zeros and constant of the file, by scipy.


    """

    f: list[float]
    whole: list[float]
    sacpz: list[float]


class ConvertCase(msgspec.Struct, kw_only=True, omit_defaults=True):
    """One instrument converted through every route; the fields of a route stay
    unset when it does not run

    Args:
        n: number of the case, its folder.
        kind: pair or integrated.
        sensor: instconfig of the sensor, or of the integrated instrument.
        datalogger: instconfig of the datalogger, None for an integrated one.
        ok: False when the case stopped on an error.
        error: the error, its type and message.
        trace: the last frames of the error.
        rate: sample rate of the channel.
        polynomial: whether the response is a polynomial.
        input: input units of the channel.
        stages: number of stages.
        xml_to_resp: whether nrlx convert wrote the RESP.
        resp_to_xml: whether nrlx convert wrote the StationXML back.
        resp_vs_original: curve of the RESP against the built channel.
        xml_vs_original: curve of the StationXML back against the built channel.
        convert_error: end of the output of the conversion that failed.
        merged_stations: stations of the StationXML back (1 expected).
        merged_channels: channel codes of the StationXML back.
        dataless_to_xml: whether nrlx convert read the dataless obspy wrote,
            None when obspy could not write it.
        dataless_vs_original: curve of the dataless against the built channel.
        dataless_error: end of the output of the dataless conversion that failed.
        dataless_writer: the error of obspy's dataless writer.
        dataless_longest_blockette: longest blockette obspy wrote, in bytes.
        dataless_overflow: whether it is over BLOCKETTE_LIMIT.
        dataless_cause: why the dataless failed: obspy's writer or the reading.
        sacpz_exit: exit code of nrlx convert to SACPZ.
        sacpz_expected: whether SACPZ can hold the channel.
        sacpz_note: the note nrlx printed with the SACPZ.
        sacpz_refusal: end of the output of the refusal.
        sacpz_inband: SACPZ against the whole channel, in the lower quarter.
        sacpz_top: SACPZ against the whole channel at the top frequency.
        sacpz_vs_scipy: the constant, poles and zeros evaluated here against
            scipy's freqs_zpk.
        sens_frequency: frequency of the stated sensitivity.
        pz_norm_frequency: normalization frequency of the first stage.
        sacpz_curve: the curves, for the report.


    """

    n: int
    kind: str
    sensor: str
    datalogger: str | None
    ok: bool = False
    error: str | None = None
    trace: str | None = None
    rate: float | None = None
    polynomial: bool | None = None
    input: str | None = None
    stages: int | None = None
    xml_to_resp: bool | None = None
    resp_to_xml: bool | None = None
    resp_vs_original: float | None = None
    xml_vs_original: float | None = None
    convert_error: str | None = None
    merged_stations: int | None = None
    merged_channels: list[str] | None = None
    dataless_to_xml: bool | None = None
    dataless_vs_original: float | None = None
    dataless_error: str | None = None
    dataless_writer: str | None = None
    dataless_longest_blockette: int | None = None
    dataless_overflow: bool | None = None
    dataless_cause: str | None = None
    sacpz_exit: int | None = None
    sacpz_expected: bool | None = None
    sacpz_note: str | None = None
    sacpz_refusal: str | None = None
    sacpz_inband: float | None = None
    sacpz_top: float | None = None
    sacpz_vs_scipy: float | None = None
    sens_frequency: float | None = None
    pz_norm_frequency: float | None = None
    sacpz_curve: SacpzCurve | None = None


def compare(original: Channel, path: Path) -> float:
    """First channel of a file against the channel built: the largest relative
    difference of the curves, or of the polynomial coefficients (0 or inf)

    Args:
        original: the channel built by nrlx.
        path: file written by nrlx convert.

    Returns:
        the difference.


    """
    channel = obspy.read_inventory(str(path))[0][0][0]
    before, after = original.response, channel.response
    if before.instrument_polynomial is not None:
        # a RESP keeps the polynomial as a stage, StationXML on the response
        again = after.instrument_polynomial or next(
            (
                stage
                for stage in after.response_stages
                if type(stage).__name__ == "PolynomialResponseStage"
            ),
            None,
        )
        same = again is not None and list(again.coefficients) == list(
            before.instrument_polynomial.coefficients
        )
        difference = 0.0 if same else float("inf")
    else:
        frequencies = grid(original.sample_rate)
        difference = deviation(curve(before, frequencies), curve(after, frequencies))

    return difference


def convert_case(nrl: Nrlx, case: ConvertCase, folder: Path) -> None:
    """Build the instrument of a case from the local copy and convert it through
    every route, filling the case

    Args:
        nrl: the NRL, with its local copy.
        case: the case, with its parts.
        folder: folder of its files.

    Raises:
        ValueError, LookupError, OSError, ArithmeticError: see CASE_ERRORS.


    """
    station = f"C{case.n:02d}"
    built, _ = nrl.response(
        sensor=[case.sensor] if case.kind == "pair" else None,
        datalogger=[case.datalogger] if case.datalogger is not None else None,
        integrated=[case.sensor] if case.kind == "integrated" else None,
        source="local",
        network="XY",
        station=station,
        location="00",
        channels=["HHZ", "HHN", "HHE"],
    )
    original = built[0][0][0]
    response = original.response
    # obspy's floats carry uncertainties: plain floats for the JSON
    case.rate = float(original.sample_rate) if original.sample_rate else None
    case.polynomial = response.instrument_polynomial is not None
    stated = response.instrument_sensitivity or response.instrument_polynomial
    case.input = stated.input_units if stated is not None else ""
    case.stages = len(response.response_stages)
    source = folder / "built.xml"
    built.write(str(source), format="STATIONXML")

    # StationXML -> RESP -> StationXML, by the command
    resp_code, resp_output = run_nrlx(
        ["convert", str(source), "-o", str(folder / "a.resp")]
    )
    xml_code, xml_output = run_nrlx(
        ["convert", str(folder / "a.resp"), "-o", str(folder / "b.xml")]
    )
    case.xml_to_resp = resp_code == 0
    case.resp_to_xml = xml_code == 0
    if resp_code == 0:
        case.resp_vs_original = compare(original, folder / "a.resp")
    if xml_code == 0:
        case.xml_vs_original = compare(original, folder / "b.xml")
        # the merged RESP of three channels is one station of three channels
        back = obspy.read_inventory(str(folder / "b.xml"))
        case.merged_stations = len(back[0].stations)
        case.merged_channels = [channel.code for channel in back[0][0]]
    if resp_code or xml_code:
        case.convert_error = (resp_output if resp_code else xml_output).strip()[-300:]

    # dataless SEED written by obspy from the RESP -> StationXML, with the longest
    # blockette obspy's writer gives
    if resp_code == 0:
        try:
            parser = Parser(str(folder / "a.resp"))
            case.dataless_longest_blockette = max(
                len(blockette.get_seed())
                for blockettes in parser.stations
                for blockette in blockettes
            )
            case.dataless_overflow = case.dataless_longest_blockette > BLOCKETTE_LIMIT
            parser.write_seed(str(folder / "c.dataless"))
        except CASE_ERRORS as err:
            case.dataless_writer = f"{type(err).__name__}: {err}"[:200]
        else:
            dataless_code, dataless_output = run_nrlx(
                ["convert", str(folder / "c.dataless"), "-o", str(folder / "d.xml")]
            )
            case.dataless_to_xml = dataless_code == 0
            if dataless_code == 0:
                case.dataless_vs_original = compare(original, folder / "d.xml")
            else:
                case.dataless_error = dataless_output.strip()[-300:]
                case.dataless_cause = (
                    "obspy's writer: blockette over 9999 bytes"
                    if case.dataless_overflow
                    else "reading"
                )

    # SACPZ: refused, or written with its note and checked against evalresp and
    # against scipy
    sacpz_code, sacpz_output = run_nrlx(
        ["convert", f"{source}#XY.{station}.00.HHZ", "-o", str(folder / "e.pz")]
    )
    case.sacpz_exit = sacpz_code
    case.sacpz_expected = not case.polynomial and case.input.upper() in SACPZ_UNITS
    if sacpz_code == 0:
        notes = [line for line in sacpz_output.splitlines() if line.startswith("note:")]
        case.sacpz_note = notes[0].removeprefix("note: ") if notes else None
        [(_, zeros, poles, constant, _)] = read_sacpz((folder / "e.pz").read_text())
        frequencies = grid(original.sample_rate)
        whole = curve(response, frequencies, output="DISP")
        # the constant, poles and zeros in rad/s, here and by scipy
        sacpz = np.array(
            [
                abs(
                    constant
                    * np.prod([2j * np.pi * frequency - zero for zero in zeros])
                    / np.prod([2j * np.pi * frequency - pole for pole in poles])
                )
                for frequency in frequencies
            ]
        )
        _, values = freqs_zpk(zeros, poles, constant, worN=2 * np.pi * frequencies)
        inband = frequencies <= 0.25 * frequencies[-1]
        case.sacpz_inband = deviation(whole[inband], sacpz[inband])
        case.sacpz_top = float(abs(sacpz[-1] / whole[-1] - 1.0))
        case.sacpz_vs_scipy = float(np.max(np.abs(sacpz / np.abs(values) - 1.0)))
        case.sens_frequency = float(response.instrument_sensitivity.frequency)
        normalization = response.response_stages[0].normalization_frequency
        case.pz_norm_frequency = float(normalization) if normalization else None
        case.sacpz_curve = SacpzCurve(
            f=frequencies.tolist(), whole=whole.tolist(), sacpz=np.abs(values).tolist()
        )
    else:
        case.sacpz_refusal = sacpz_output.strip()[-200:]
    case.ok = True


def main() -> None:
    """Run the battery: the arguments, the cases, convert.json in the output folder
    and the numbers of the paper on the standard output


    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261115)
    parser.add_argument("--pairs", type=int, default=40)
    parser.add_argument("--integrated", type=int, default=6)
    arguments = parser.parse_args()
    warnings.simplefilter("ignore")
    work = arguments.out / "convert"
    work.mkdir(parents=True, exist_ok=True)
    nrl = Nrlx.from_cache(arguments.cache_root)

    # random pairs and integrated instruments, from the seed
    sensors, dataloggers, integrated = list(), list(), list()
    for element, _, _, configuration in nrl.catalog.get_configurations():
        match element.name:
            case "sensor":
                sensors.append(configuration.instconfig)
            case "datalogger":
                dataloggers.append(configuration.instconfig)
            case "integrated":
                integrated.append(configuration.instconfig)
    rng = random.Random(arguments.seed)
    pairs = zip(
        rng.sample(sensors, arguments.pairs),
        rng.sample(dataloggers, arguments.pairs),
        strict=True,
    )
    cases = [
        ConvertCase(n=number, kind="pair", sensor=sensor, datalogger=datalogger)
        for number, (sensor, datalogger) in enumerate(pairs)
    ]
    cases += [
        ConvertCase(
            n=len(cases) + number, kind="integrated", sensor=instconfig, datalogger=None
        )
        for number, instconfig in enumerate(
            rng.sample(integrated, arguments.integrated)
        )
    ]

    # each case in its folder; an error stops the case, not the battery
    for case in cases:
        folder = work / f"{case.n:02d}"
        folder.mkdir(exist_ok=True)
        try:
            convert_case(nrl, case, folder)
        except CASE_ERRORS as err:
            case.error = f"{type(err).__name__}: {err}"
            case.trace = traceback.format_exc(limit=3)
        print(
            case.n,
            case.ok,
            case.resp_vs_original,
            case.xml_vs_original,
            case.dataless_vs_original,
            case.sacpz_exit,
            case.error or "",
            flush=True,
        )
    (arguments.out / "convert.json").write_bytes(
        msgspec.json.format(msgspec.json.encode(cases), indent=1)
    )

    # the numbers of the paper
    done = [case for case in cases if case.sacpz_inband is not None]
    tried = [case for case in cases if case.dataless_overflow is not None]
    failed = [case for case in tried if case.dataless_to_xml is False]
    print(
        f"SACPZ: {len(done)} written, "
        f"{sum((case.sacpz_inband or 0.0) > 0.05 for case in done)} above 5 % in band, "
        f"scipy max {max((case.sacpz_vs_scipy or 0.0) for case in done):.1e}"
    )
    print(
        f"dataless: {len(tried)} written, "
        f"{sum(bool(case.dataless_overflow) for case in tried)} with a blockette over "
        f"{BLOCKETTE_LIMIT} bytes, {len(failed)} failed, "
        f"{sum(not case.dataless_overflow for case in failed)} of them by the reading"
    )


if __name__ == "__main__":
    main()
