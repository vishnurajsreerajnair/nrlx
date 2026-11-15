"""End-to-end battery of the builds of nrlx on random NRL parts: the service, the
local copy, a part from a file, StationXML and RESP read back

Each pair of a sensor and a datalogger is built by the service, from the local copy
and with the sensor from its file and the datalogger from the service; single
parts of every element by the service and from the local copy. The requests to
the service are spaced by --pause seconds. Writes battery.json, which
cli_battery.py reads.

Example:

    python scripts/e2e/build_battery.py --cache-root CACHE --out OUT


"""

from __future__ import annotations

import argparse
import random
import time
import traceback
import warnings
from pathlib import Path

import msgspec
import numpy as np
import numpy.typing as npt
import obspy
from common import CASE_ERRORS, curve, deviation, grid
from obspy.core.inventory.response import Response

from nrlx.core.combine import output_rate
from nrlx.io.inventory import placeholder_inventory, read_part
from nrlx.io.resp import write_resp
from nrlx.models.nrlx import Nrlx

# the single parts of each element, and how many
SINGLES = [("sensor", 8), ("datalogger", 6), ("integrated", 3), ("soh", 3)]


class PairCurves(msgspec.Struct, kw_only=True):
    """The curves of a pair, for the report

    Args:
        f: frequencies in Hz.
        service: amplitude of the service build, None for a polynomial.
        local: amplitude of the local build, None for a polynomial.


    """

    f: list[float]
    service: list[float] | None
    local: list[float] | None


class PairCase(msgspec.Struct, kw_only=True, omit_defaults=True):
    """A sensor and a datalogger built in three ways

    Args:
        n: number of the pair, its folder.
        sensor: instconfig of the sensor.
        datalogger: instconfig of the datalogger.
        requests: requests made to the service.
        ok: False when the case stopped on an error.
        error: the error, its type and message.
        trace: the last frames of the error.
        rate: sample rate of the local build.
        stages: number of stages of the local build.
        polynomial: whether the response is a polynomial.
        input: input units of the first stage.
        same_stages: whether the service and local builds have the same stages
            (type, gain, units, decimation).
        local_equals_mixed: whether the build with the sensor from its file
            equals the local one: stages, curve and notes.
        curve_service_vs_local: curve of the local build against the service one.
        service_self: stated sensitivity of the service build against evalresp at
            its frequency, minus 1.
        local_self: the same for the local build.
        service_sensitivity: value and frequency of the service sensitivity.
        local_sensitivity: value and frequency of the local sensitivity.
        xml_roundtrip: curve of the local build written as StationXML and read
            back by obspy.
        resp_roundtrip: the same as RESP, written by nrlx.
        notes: the notes of the local build.
        curves: the curves, for the report.
        poly_service: polynomial coefficients of the service build.
        poly_local: polynomial coefficients of the local build.


    """

    n: int
    sensor: str
    datalogger: str
    requests: int = 0
    ok: bool = False
    error: str | None = None
    trace: str | None = None
    rate: float | None = None
    stages: int | None = None
    polynomial: bool | None = None
    input: str | None = None
    same_stages: bool | None = None
    local_equals_mixed: bool | None = None
    curve_service_vs_local: float | None = None
    service_self: float | None = None
    local_self: float | None = None
    service_sensitivity: tuple[float, float] | None = None
    local_sensitivity: tuple[float, float] | None = None
    xml_roundtrip: float | None = None
    resp_roundtrip: float | None = None
    notes: list[str] | None = None
    curves: PairCurves | None = None
    poly_service: list[float] | None = None
    poly_local: list[float] | None = None


class SingleCase(msgspec.Struct, kw_only=True, omit_defaults=True):
    """A single part built by the service and from the local copy

    Args:
        element: sensor, datalogger, integrated or soh.
        instconfig: instconfig of the part.
        requests: requests made to the service.
        ok: False when the case stopped on an error.
        error: the error, its type and message.
        same_stages: whether both builds have the same stages.
        curve: curve of the local build against the service one, None without
            a sensitivity or stages.
        same_sensitivity: whether both state the same sensitivity.
        stages: number of stages of the local build.


    """

    element: str
    instconfig: str
    requests: int = 0
    ok: bool = False
    error: str | None = None
    same_stages: bool | None = None
    curve: float | None = None
    same_sensitivity: bool | None = None
    stages: int | None = None


class Battery(msgspec.Struct, kw_only=True):
    """The result of the battery, battery.json

    Args:
        pairs: the pairs.
        singles: the single parts.
        requests: requests made to the service in all.


    """

    pairs: list[PairCase]
    singles: list[SingleCase]
    requests: int


def signature(
    response: Response,
) -> list[tuple[str, float | None, str, str, int | None]]:
    """What two builds of the same parts must share, stage by stage

    Args:
        response: the response.

    Returns:
        for each stage its type, gain, input and output units, decimation factor.


    """
    stages = [
        (
            type(stage).__name__,
            float(stage.stage_gain) if stage.stage_gain is not None else None,
            (stage.input_units or "").upper(),
            (stage.output_units or "").upper(),
            stage.decimation_factor,
        )
        for stage in response.response_stages
    ]

    return stages


def amplitude(
    response: Response, frequencies: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64] | None:
    """Curve of a response, None for a polynomial (no sensitivity)

    Args:
        response: the response.
        frequencies: frequencies in Hz.

    Returns:
        the amplitude at each frequency, or None.


    """
    values = (
        curve(response, frequencies)
        if response.instrument_sensitivity is not None
        else None
    )

    return values


def self_consistency(response: Response) -> float | None:
    """Stated sensitivity of a response over the one evalresp computes at its
    frequency, minus 1

    Args:
        response: the response.

    Returns:
        the difference, None without a sensitivity.


    """
    sensitivity = response.instrument_sensitivity
    difference = None
    if sensitivity is not None:
        computed = curve(response, np.array([sensitivity.frequency]))[0]
        difference = float(sensitivity.value / computed - 1.0)

    return difference


def read_back(response: Response, path: Path) -> Response:
    """A response written as a placeholder channel and read back by obspy:
    StationXML by obspy for a .xml, RESP by nrlx for a .resp

    Args:
        response: the response.
        path: the file to write.

    Returns:
        the response read back.


    """
    inventory = placeholder_inventory(response, output_rate(response.response_stages))
    if path.suffix == ".xml":
        inventory.write(str(path), format="STATIONXML")
    else:
        path.write_text(write_resp(inventory))
    again: Response = obspy.read_inventory(str(path))[0][0][0].response

    return again


def pair_case(nrl: Nrlx, case: PairCase, folder: Path, pause: float) -> None:
    """Build a pair in the three ways and compare the builds, filling the case

    Args:
        nrl: the NRL, with its local copy.
        case: the case, with its parts.
        folder: folder of its files.
        pause: seconds before each request to the service.

    Raises:
        ValueError, LookupError, OSError, ArithmeticError, httpx.HTTPError: see
            CASE_ERRORS.


    """
    sensor, datalogger = [case.sensor], [case.datalogger]
    time.sleep(pause)
    case.requests += 1
    service, _ = nrl.response(sensor=sensor, datalogger=datalogger)
    service.write(str(folder / "service.xml"), format="STATIONXML")
    local, notes = nrl.response(sensor=sensor, datalogger=datalogger, source="local")
    local.write(str(folder / "local.xml"), format="STATIONXML")
    sensor_file = read_part(nrl.local_file(case.sensor))
    time.sleep(pause)
    case.requests += 1
    mixed, mixed_notes = nrl.response(
        sensor_response=sensor_file, datalogger=datalogger
    )

    # the curves of the three builds and of the local one read back
    from_service = service[0][0][0].response
    from_local = local[0][0][0].response
    from_mixed = mixed[0][0][0].response
    # obspy's floats carry uncertainties: plain floats for the JSON
    rate = local[0][0][0].sample_rate
    case.rate = float(rate) if rate else None
    frequencies = grid(case.rate)
    service_curve = amplitude(from_service, frequencies)
    local_curve = amplitude(from_local, frequencies)
    mixed_curve = amplitude(from_mixed, frequencies)
    xml_curve = amplitude(read_back(from_local, folder / "nrlx.xml"), frequencies)
    resp_curve = amplitude(read_back(from_local, folder / "nrlx.resp"), frequencies)
    case.stages = len(from_local.response_stages)
    case.polynomial = from_local.instrument_polynomial is not None
    case.input = from_local.response_stages[0].input_units or ""
    case.same_stages = signature(from_service) == signature(from_local)
    case.local_equals_mixed = (
        signature(from_local) == signature(from_mixed)
        and notes == mixed_notes
        and (
            local_curve is None
            or mixed_curve is None
            or deviation(local_curve, mixed_curve) == 0.0
        )
    )
    case.service_self = self_consistency(from_service)
    case.local_self = self_consistency(from_local)
    case.notes = notes
    case.curves = PairCurves(
        f=frequencies.tolist(),
        service=None if service_curve is None else service_curve.tolist(),
        local=None if local_curve is None else local_curve.tolist(),
    )
    if local_curve is not None and service_curve is not None:
        case.curve_service_vs_local = deviation(service_curve, local_curve)
    if local_curve is not None and xml_curve is not None:
        case.xml_roundtrip = deviation(local_curve, xml_curve)
    if local_curve is not None and resp_curve is not None:
        case.resp_roundtrip = deviation(local_curve, resp_curve)

    # the sensitivities, or the polynomials
    if case.polynomial:
        case.poly_service = [
            float(value) for value in from_service.instrument_polynomial.coefficients
        ]
        case.poly_local = [
            float(value) for value in from_local.instrument_polynomial.coefficients
        ]
    else:
        stated = from_service.instrument_sensitivity
        case.service_sensitivity = (float(stated.value), float(stated.frequency))
        stated = from_local.instrument_sensitivity
        case.local_sensitivity = (float(stated.value), float(stated.frequency))
    case.ok = True


def single_case(nrl: Nrlx, case: SingleCase, pause: float) -> None:
    """Build a single part by the service and from the local copy and compare the
    builds, filling the case

    Args:
        nrl: the NRL, with its local copy.
        case: the case, with its part.
        pause: seconds before the request to the service.

    Raises:
        ValueError, LookupError, OSError, ArithmeticError, httpx.HTTPError: see
            CASE_ERRORS.


    """
    part = [case.instconfig]
    time.sleep(pause)
    case.requests += 1
    match case.element:
        case "sensor":
            service, _ = nrl.response(sensor=part)
            local, _ = nrl.response(sensor=part, source="local")
        case "datalogger":
            service, _ = nrl.response(datalogger=part)
            local, _ = nrl.response(datalogger=part, source="local")
        case "integrated":
            service, _ = nrl.response(integrated=part)
            local, _ = nrl.response(integrated=part, source="local")
        case _:
            service, _ = nrl.response(soh=part)
            local, _ = nrl.response(soh=part, source="local")
    from_service, from_local = service[0][0][0].response, local[0][0][0].response
    frequencies = grid(local[0][0][0].sample_rate)
    stated, stated_local = (
        from_service.instrument_sensitivity,
        from_local.instrument_sensitivity,
    )
    case.same_stages = signature(from_service) == signature(from_local)
    if stated is not None and from_service.response_stages:
        case.curve = deviation(
            curve(from_service, frequencies), curve(from_local, frequencies)
        )
    case.same_sensitivity = (stated is None and stated_local is None) or (
        stated is not None
        and stated_local is not None
        and stated.value == stated_local.value
    )
    case.stages = len(from_local.response_stages)
    case.ok = True


def main() -> None:
    """Run the battery: the arguments, the cases, battery.json in the output folder
    and a line per case on the standard output


    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--pairs", type=int, default=30)
    parser.add_argument("--pause", type=float, default=0.3)
    arguments = parser.parse_args()
    warnings.simplefilter("ignore")
    nrl = Nrlx.from_cache(arguments.cache_root)

    # the instconfigs of each element, and random picks from the seed
    by_element: dict[str, list[str]] = dict()
    for element, _, _, configuration in nrl.catalog.get_configurations():
        by_element.setdefault(element.name, []).append(configuration.instconfig)
    rng = random.Random(arguments.seed)
    sensors = rng.sample(by_element["sensor"], arguments.pairs)
    dataloggers = rng.sample(by_element["datalogger"], arguments.pairs)
    pairs = [
        PairCase(n=number, sensor=sensor, datalogger=datalogger)
        for number, (sensor, datalogger) in enumerate(
            zip(sensors, dataloggers, strict=True)
        )
    ]
    singles = [
        SingleCase(element=element, instconfig=instconfig)
        for element, count in SINGLES
        for instconfig in rng.sample(by_element[element], count)
    ]

    # each case; an error stops the case, not the battery
    for case in pairs:
        folder = arguments.out / "pairs" / f"{case.n:02d}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            pair_case(nrl, case, folder, arguments.pause)
        except CASE_ERRORS as err:
            case.error = f"{type(err).__name__}: {err}"
            case.trace = traceback.format_exc(limit=3)
        print(case.n, case.ok, case.sensor, case.datalogger, case.error or "")
    for single in singles:
        try:
            single_case(nrl, single, arguments.pause)
        except CASE_ERRORS as err:
            single.error = f"{type(err).__name__}: {err}"
        print(single.element, single.ok, single.instconfig, single.error or "")
    requests = sum(case.requests for case in pairs) + sum(
        single.requests for single in singles
    )
    battery = Battery(pairs=pairs, singles=singles, requests=requests)
    (arguments.out / "battery.json").write_bytes(
        msgspec.json.format(msgspec.json.encode(battery), indent=1)
    )
    print("requests", requests)


if __name__ == "__main__":
    main()
