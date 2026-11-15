"""Health checks of the response files

Tier 1: structural checks of the content, whether it is well-formed RESP or XML
with the parts of a response, for a file obspy cannot read. Tier 2: physical checks
of each channel, its amplitude, its chains of units and rates, its poles and zeros,
and its codes. Tier 3: each channel against the NRL nominal response of the parts
it is built from.


"""

from __future__ import annotations

import cmath
import math
import re
from itertools import pairwise
from typing import Literal
from xml.etree import ElementTree

from obspy.core.inventory.response import (
    CoefficientsTypeResponseStage,
    FIRResponseStage,
    PolesZerosResponseStage,
    Response,
    ResponseStage,
)

from nrlx.core.combine import (
    FLAT_BAND_FRACTION,
    band_fraction,
    normalization_values,
    sensor_stages,
    stated_ratio,
)
from nrlx.core.gain import (
    denominator_coefficients,
    fir_scale,
    numerator_coefficients,
)
from nrlx.core.seed import band_codes
from nrlx.schema.response import ResponseFormat

# info: a check that does not apply (no rate, no sensor stages, a polynomial)
Severity = Literal["ok", "info", "warning", "error"]

# a line of a RESP blockette, for example B052F03
BLOCKETTE_LINE = re.compile(r"^B\d{3}F\d{2}\b", re.MULTILINE)


def guess_format(content: bytes) -> ResponseFormat:
    """Format a file that obspy cannot read was meant to be, for the tier 1 checks

    Args:
        content: content of the file.

    Returns:
        stationxml for content starting with < that is not an HTML page (an error
        page saved as a response goes to the RESP checks, which say so), else resp.


    """
    head = content.lstrip()[:1000].lower()
    guessed: ResponseFormat = (
        "stationxml" if head.startswith(b"<") and b"<html" not in head else "resp"
    )

    return guessed


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


# a stated sensitivity this far from its stages is an error
SENSITIVITY_ERROR = 0.01

# a zero this close to a pole, relative to the pole, cancels it
CANCEL_TOLERANCE = 1e-6

# two rates of a decimation chain this close, relative, are the same
RATE_TOLERANCE = 1e-9

# the units of the output of a channel, and of the input of each kind of sensor
COUNTS = ["COUNT", "COUNTS"]
VELOCITY = ["M/S", "M/SEC"]
ACCELERATION = ["M/S**2", "M/SEC**2"]
PRESSURE = ["PA", "HPA", "KPA", "MBAR"]


def check_amplitude(
    response: Response, sample_rate: float | None
) -> list[tuple[Severity, str]]:
    """Checks of the amplitude of a channel: its stated sensitivity against its
    stages, the normalization factors, where the sensitivity is, and the FIRs

    Args:
        response: response of the channel.
        sample_rate: sample rate of the channel, None when unknown.

    Returns:
        severity and message of each check, in check order.


    """
    findings: list[tuple[Severity, str]] = list()
    sensitivity = response.instrument_sensitivity
    stages = list(response.response_stages)

    # a polynomial has no sensitivity; any other response needs one above 0
    if sensitivity is None and response.instrument_polynomial is not None:
        findings.append(("info", "polynomial response: no sensitivity to check"))
    elif sensitivity is None:
        findings.append(("error", "no sensitivity and no polynomial"))
    elif not sensitivity.value or float(sensitivity.value) <= 0.0:
        findings.append(("error", f"sensitivity {sensitivity.value} is not above 0"))
    else:
        value = float(sensitivity.value)
        frequency = float(sensitivity.frequency or 0.0)

        # the stated sensitivity against what its stages give, by evalresp's rules
        try:
            stated = stated_ratio(response)
        except ValueError as err:
            findings.append(("warning", f"the sensitivity cannot be checked: {err}"))
        else:
            match stated:
                case None:
                    findings.append(("info", "no stages to check the sensitivity"))
                case computed, ratio if abs(ratio - 1.0) > SENSITIVITY_ERROR:
                    findings.append(
                        (
                            "error",
                            f"stated {value:.6g} at {frequency:g} Hz, the stages "
                            f"give {computed:.6g} (x{ratio:.4g}): remove_response "
                            "and remove_sensitivity disagree",
                        )
                    )
                case _, ratio:
                    findings.append(
                        (
                            "ok",
                            f"sensitivity {value:.6g} at {frequency:g} Hz, as its "
                            f"stages give (x{ratio:.6g})",
                        )
                    )

        # the sensitivity must be at a frequency the channel records
        if sample_rate and frequency >= sample_rate / 2.0:
            findings.append(
                (
                    "warning",
                    f"sensitivity at {frequency:g} Hz, at or above the Nyquist "
                    f"frequency of {sample_rate:g} sps",
                )
            )

        # and in the flat band of the sensor
        try:
            sensor = sensor_stages(response)
        except ValueError:
            findings.append(("info", "no voltage output: flat band not checked"))
        else:
            fraction = band_fraction(sensor, frequency)
            if fraction < FLAT_BAND_FRACTION:
                findings.append(
                    (
                        "warning",
                        f"the sensor gives {fraction * 100:.3g}% of its gain at "
                        f"{frequency:g} Hz: the sensitivity is out of its flat band",
                    )
                )
            else:
                findings.append(
                    ("ok", f"sensitivity in the sensor's flat band ({fraction:.3g})")
                )

    # each poles and zeros stage worth its gain at its normalization frequency
    for number, frequency, factor in normalization_values(stages):
        findings.append(
            (
                "warning",
                f"stage {number}: the normalization factor gives x{factor:.6g} of "
                f"its gain at {frequency:g} Hz: obspy and the NRL service give "
                "different amplitudes",
            )
        )

    # a FIR evalresp normalizes, because its coefficients do not sum to 1
    for stage in stages:
        scale = fir_scale(stage)
        if scale != 1.0:
            findings.append(
                (
                    "warning",
                    f"stage {stage.stage_sequence_number}: the FIR coefficients sum "
                    f"to {1.0 / scale:.6g}, not 1: evalresp divides them by the sum",
                )
            )

    return findings


def check_chains(
    response: Response, sample_rate: float | None
) -> list[tuple[Severity, str]]:
    """Checks of the chains of a channel: stage numbers, units and sample rates

    Args:
        response: response of the channel.
        sample_rate: sample rate of the channel, None when unknown.

    Returns:
        severity and message of each check, in check order.


    """
    findings: list[tuple[Severity, str]] = list()
    stages = list(response.response_stages)
    if not stages:
        findings.append(("info", "no stages"))
    else:
        # the stages numbered 1 to N
        numbers = [int(stage.stage_sequence_number) for stage in stages]
        if numbers == list(range(1, len(stages) + 1)):
            findings.append(("ok", f"stages numbered 1 to {len(stages)}"))
        else:
            findings.append(("error", f"stages numbered {numbers}, not 1 to N"))

        # each stage takes the units the previous one gives
        breaks = [
            f"stage {after.stage_sequence_number} takes {after.input_units or '-'} "
            f"after {before.output_units or '-'}"
            for before, after in pairwise(stages)
            if str(before.output_units).upper() != str(after.input_units).upper()
        ]
        chain = " -> ".join(
            [str(stages[0].input_units)] + [str(stage.output_units) for stage in stages]
        )
        if breaks:
            findings.append(("error", f"units break: {'; '.join(breaks)}"))
        else:
            findings.append(("ok", f"units {chain}"))

        # the channel gives counts
        last = str(stages[-1].output_units).upper()
        if last not in COUNTS:
            findings.append(("error", f"the last stage gives {last}, not counts"))

        # the sensitivity is in the units of the stages
        sensitivity = response.instrument_sensitivity
        if sensitivity is not None:
            given = (
                str(sensitivity.input_units).upper(),
                str(sensitivity.output_units).upper(),
            )
            expected = (str(stages[0].input_units).upper(), last)
            if given != expected:
                findings.append(
                    (
                        "error",
                        f"sensitivity in {given[0]} -> {given[1]}, the stages in "
                        f"{expected[0]} -> {expected[1]}",
                    )
                )

        # each digital stage has its decimation
        digital = [
            stage
            for stage in stages
            if isinstance(stage, CoefficientsTypeResponseStage | FIRResponseStage)
            or (
                isinstance(stage, PolesZerosResponseStage)
                and "DIGITAL" in str(stage.pz_transfer_function_type).upper()
            )
        ]
        missing = [
            str(stage.stage_sequence_number)
            for stage in digital
            if not stage.decimation_input_sample_rate or not stage.decimation_factor
        ]
        if missing:
            findings.append(
                ("error", f"digital stages without decimation: {', '.join(missing)}")
            )

        # each decimation takes the rate the previous one gives, and the last one
        # gives the rate of the channel
        rate = None
        jumps = list()
        for stage in stages:
            if stage.decimation_input_sample_rate and stage.decimation_factor:
                given_rate = float(stage.decimation_input_sample_rate)
                if rate is not None and not math.isclose(
                    given_rate, rate, rel_tol=RATE_TOLERANCE
                ):
                    jumps.append(
                        f"stage {stage.stage_sequence_number} takes {given_rate:g} "
                        f"sps after {rate:g}"
                    )
                rate = given_rate / int(stage.decimation_factor)
        if jumps:
            findings.append(
                (
                    "warning",
                    f"rates break: {'; '.join(jumps)} (evalresp takes each stage at "
                    "its own rate)",
                )
            )
        if (
            rate is not None
            and sample_rate
            and not math.isclose(rate, sample_rate, rel_tol=RATE_TOLERANCE)
        ):
            findings.append(
                (
                    "error",
                    f"the decimations give {rate:g} sps, the channel {sample_rate:g}",
                )
            )
        elif rate is not None and not jumps:
            findings.append(("ok", f"decimations chained down to {rate:g} sps"))

    return findings


def check_poles(response: Response) -> list[tuple[Severity, str]]:
    """Checks of the poles and zeros stages of a channel

    Args:
        response: response of the channel.

    Returns:
        severity and message of each check, in check order.


    """
    findings: list[tuple[Severity, str]] = list()
    for stage in response.response_stages:
        if isinstance(stage, PolesZerosResponseStage) and (stage.poles or stage.zeros):
            findings += check_poles_zeros(
                [complex(zero) for zero in stage.zeros],
                [complex(pole) for pole in stage.poles],
                "DIGITAL" in str(stage.pz_transfer_function_type).upper(),
                f"stage {stage.stage_sequence_number}",
            )
    if not findings:
        findings.append(("info", "no poles and zeros"))

    return findings


def check_poles_zeros(
    zeros: list[complex], poles: list[complex], digital: bool, where: str
) -> list[tuple[Severity, str]]:
    """Checks of a set of poles and zeros: stable poles, no zero cancelling a pole

    Args:
        zeros: the zeros.
        poles: the poles.
        digital: True for a Z transform, False for a Laplace transform.
        where: what holds them, for the messages (for example "stage 1").

    Returns:
        severity and message of each check, in check order.


    """
    findings: list[tuple[Severity, str]] = list()

    # an analog pole on the right half plane, or a digital one outside the unit
    # circle, makes the filter unstable
    unstable = [
        pole for pole in poles if (abs(pole) > 1.0 if digital else pole.real > 0.0)
    ]
    if unstable:
        listed = ", ".join(f"{pole:.6g}" for pole in unstable)
        findings.append(("error", f"{where}: unstable poles {listed}"))
    else:
        findings.append(("ok", f"{where}: {len(poles)} poles, all stable"))

    # a zero on a pole does nothing, often a typing slip
    cancelled = [
        pole
        for pole in poles
        for zero in zeros
        if abs(zero - pole) <= CANCEL_TOLERANCE * max(1.0, abs(pole))
    ]
    if cancelled:
        listed = ", ".join(f"{pole:.6g}" for pole in cancelled)
        findings.append(("warning", f"{where}: zeros cancel the poles {listed}"))

    return findings


def check_sacpz(
    zeros: list[complex], poles: list[complex], constant: float
) -> list[tuple[Severity, str]]:
    """Checks of a channel of a SACPZ file: its poles and zeros, and its constant

    Args:
        zeros: zeros in rad/s.
        poles: poles in rad/s.
        constant: the CONSTANT, A0 x the overall sensitivity.

    Returns:
        severity and message of each check, in check order.


    """
    findings = check_poles_zeros(zeros, poles, False, "SACPZ")
    if constant <= 0.0:
        findings.append(("error", f"CONSTANT {constant:g} is not above 0"))
    else:
        findings.append(("ok", f"CONSTANT {constant:.6g}"))
    findings.append(
        ("info", "SACPZ has no stages: amplitude and chains need StationXML or RESP")
    )

    return findings


def check_codes(
    code: str, sample_rate: float | None, input_units: str | None
) -> list[tuple[Severity, str]]:
    """Checks of a channel code against the SEED norm: its band for the sample rate,
    its instrument for the input units

    Args:
        code: channel code, for example HHZ.
        sample_rate: sample rate of the channel, None when unknown.
        input_units: input units of the channel, None when unknown (SACPZ).

    Returns:
        severity and message of each check, in check order.


    """
    findings: list[tuple[Severity, str]] = list()

    # the band, first letter, from the sample rate
    codes = band_codes(sample_rate) if sample_rate else []
    if not codes:
        findings.append(("info", f"band {code[:1]}: no band in the norm to compare"))
    elif code[:1] in codes:
        findings.append(("ok", f"band {code[:1]} for {sample_rate:g} sps"))
    else:
        findings.append(
            (
                "warning",
                f"band {code[:1]} for {sample_rate:g} sps: the SEED norm gives "
                f"{' or '.join(codes)}",
            )
        )

    # the instrument, second letter, from the input units
    match code[1:2]:
        case "H" | "L" | "P":
            kind, expected = "a seismometer", VELOCITY
        case "N":
            kind, expected = "an accelerometer", ACCELERATION
        case "D":
            kind, expected = "a pressure sensor", PRESSURE
        case _:
            kind, expected = "", []
    units = (input_units or "").upper()
    if not expected or not units:
        findings.append(("info", f"instrument {code[1:2]}: units not compared"))
    elif units in expected:
        findings.append(("ok", f"instrument {code[1:2]} ({kind}) in {units}"))
    else:
        findings.append(
            (
                "warning",
                f"instrument {code[1:2]} is {kind}, in {' or '.join(expected)}, "
                f"not {units}",
            )
        )

    return findings


# a curve this far from the nominal one, in band, is a warning (a calibration can
# explain it): amplitude relative, phase in degrees
NOMINAL_AMPLITUDE = 0.01
NOMINAL_PHASE = 1.0

# two stage gains this close, relative, are the same
STAGE_TOLERANCE = 1e-6


def check_nominal_kind(
    response: Response,
    nominal: Response,
    sample_rate: float | None,
    nominal_rate: float | None,
) -> list[tuple[Severity, str]]:
    """Checks of a channel against its nominal response for what no calibration
    changes: the input units, the output rate, the poles and zeros of the sensor

    Args:
        response: response of the channel.
        nominal: nominal response of the NRL parts it is built from.
        sample_rate: sample rate of the channel, None when unknown.
        nominal_rate: sample rate of the nominal, None without digital stages.

    Returns:
        severity and message of each check, in check order.


    """
    findings: list[tuple[Severity, str]] = list()
    stages = list(response.response_stages)
    nominal_stages = list(nominal.response_stages)

    # the input units
    units = str(stages[0].input_units).upper() if stages else ""
    nominal_units = str(nominal_stages[0].input_units).upper() if nominal_stages else ""
    if units == nominal_units:
        findings.append(("ok", f"input in {units}, as the nominal"))
    else:
        findings.append(("error", f"input in {units}, the nominal in {nominal_units}"))

    # the output rate
    if (
        sample_rate
        and nominal_rate
        and not math.isclose(sample_rate, nominal_rate, rel_tol=RATE_TOLERANCE)
    ):
        findings.append(
            ("error", f"{sample_rate:g} sps, the nominal {nominal_rate:g} sps")
        )

    # the poles and zeros of the sensor, the first stage of them: their kind and
    # their number
    first = next(
        (stage for stage in stages if isinstance(stage, PolesZerosResponseStage)),
        None,
    )
    nominal_first = next(
        (
            stage
            for stage in nominal_stages
            if isinstance(stage, PolesZerosResponseStage)
        ),
        None,
    )
    shape = (
        f"{first.pz_transfer_function_type}, {len(first.poles)} poles, "
        f"{len(first.zeros)} zeros"
        if first is not None
        else "none"
    )
    nominal_shape = (
        f"{nominal_first.pz_transfer_function_type}, {len(nominal_first.poles)} "
        f"poles, {len(nominal_first.zeros)} zeros"
        if nominal_first is not None
        else "none"
    )
    if shape != nominal_shape:
        findings.append(
            ("error", f"sensor poles and zeros: {shape}; the nominal: {nominal_shape}")
        )

    return findings


def check_nominal_curve(
    frequencies: list[float], values: list[complex], nominal_values: list[complex]
) -> list[tuple[Severity, str]]:
    """Checks of the curve of a channel against its nominal one: the largest
    differences of amplitude and of phase in band

    Args:
        frequencies: frequencies of the check in Hz, in band.
        values: complex response of the channel at the frequencies.
        nominal_values: complex response of the nominal at the frequencies.

    Returns:
        severity and message of each check, in check order.


    """
    # the ratio and the phase difference at each frequency, the phase in -180..180
    differences = [
        (
            frequency,
            abs(value) / abs(nominal) - 1.0,
            math.degrees(cmath.phase(value / nominal)),
        )
        for frequency, value, nominal in zip(
            frequencies, values, nominal_values, strict=True
        )
        if value and nominal
    ]
    findings: list[tuple[Severity, str]] = list()
    if not differences:
        findings.append(("info", "no curve to compare with the nominal"))
    else:
        at, amplitude, _ = max(differences, key=lambda row: abs(row[1]))
        if abs(amplitude) > NOMINAL_AMPLITUDE:
            findings.append(
                (
                    "warning",
                    f"amplitude {amplitude * 100:+.3g}% from the nominal at {at:g} Hz",
                )
            )
        else:
            findings.append(
                ("ok", f"amplitude within {abs(amplitude) * 100:.2g}% of the nominal")
            )
        at, _, phase = max(differences, key=lambda row: abs(row[2]))
        if abs(phase) > NOMINAL_PHASE:
            findings.append(
                ("warning", f"phase {phase:+.3g} deg from the nominal at {at:g} Hz")
            )
        else:
            findings.append(("ok", f"phase within {abs(phase):.2g} deg of the nominal"))

    return findings


def stage_changes(
    stages: list[ResponseStage], nominal_stages: list[ResponseStage]
) -> list[str]:
    """Stages of a channel that differ from those of its nominal response

    Args:
        stages: stages of the channel.
        nominal_stages: stages of the nominal.

    Returns:
        for each stage that differs, its number and what differs (type, gain,
        poles and zeros, coefficients, decimation); first the number of stages
        when it differs.


    """
    changes = list()
    if len(stages) != len(nominal_stages):
        changes.append(f"{len(stages)} stages, the nominal {len(nominal_stages)}")
    for stage, nominal in zip(stages, nominal_stages, strict=False):
        what = list()

        # the type, and with the same type the gain, the filter and the decimation
        if type(stage) is not type(nominal):
            what.append(f"{type(stage).__name__} for {type(nominal).__name__}")
        else:
            gain, nominal_gain = float(stage.stage_gain), float(nominal.stage_gain)
            if not math.isclose(gain, nominal_gain, rel_tol=STAGE_TOLERANCE):
                what.append(f"gain {gain:g} for {nominal_gain:g}")
            if (
                isinstance(stage, PolesZerosResponseStage)
                and isinstance(nominal, PolesZerosResponseStage)
                and (
                    [complex(pole) for pole in stage.poles]
                    != [complex(pole) for pole in nominal.poles]
                    or [complex(zero) for zero in stage.zeros]
                    != [complex(zero) for zero in nominal.zeros]
                )
            ):
                what.append("poles and zeros")
            filters = CoefficientsTypeResponseStage | FIRResponseStage
            if (
                isinstance(stage, filters)
                and isinstance(nominal, filters)
                and (
                    numerator_coefficients(stage),
                    denominator_coefficients(stage),
                )
                != (
                    numerator_coefficients(nominal),
                    denominator_coefficients(nominal),
                )
            ):
                what.append("coefficients")
            if (stage.decimation_input_sample_rate, stage.decimation_factor) != (
                nominal.decimation_input_sample_rate,
                nominal.decimation_factor,
            ):
                what.append("decimation")
        if what:
            changes.append(f"stage {stage.stage_sequence_number}: {', '.join(what)}")

    return changes
