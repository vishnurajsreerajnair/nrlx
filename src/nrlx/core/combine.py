"""Combination of responses: the requests to the /combine endpoint of the service,
and the combination of a sensor and a datalogger done by nrlx


"""

from __future__ import annotations

import copy
import math

from obspy.core.inventory.response import (
    InstrumentPolynomial,
    InstrumentSensitivity,
    PolesZerosResponseStage,
    PolynomialResponseStage,
    Response,
    ResponseStage,
)

from nrlx.core.gain import response_amplitude, transfer

# the units of a voltage, where a sensor ends and a datalogger starts
VOLTAGES = ["V", "MV", "UV", "NV"]

# a normalization factor this far from normalizing its stage is corrected, and
# noted from NORMALIZATION_NOTED (below, the rounding of the factor in the files)
NORMALIZATION_TOLERANCE = 1e-6
NORMALIZATION_NOTED = 1e-3

# the sensitivity frequency stays at most this fraction of the output rate
MAX_RATE_FRACTION = 0.1

# below this fraction of its gain, the sensor is out of its flat band
FLAT_BAND_FRACTION = 0.5

# a stated sensitivity this far from its stages is noted
SENSITIVITY_NOTED = 1e-3


def cascade_instconfig(instconfigs: list[str]) -> str:
    """instconfig of a response: the instconfigs of its parts, cascaded

    The /combine endpoint cascades the responses of the instconfigs joined by a colon
    in a single channel, the sensor before the datalogger: this is the service
    contract, not an nrlx convention.

    Args:
        instconfigs: exact instconfigs of the parts, in the order of the signal.

    Returns:
        instconfig of the response.


    """
    instconfig = ":".join(instconfigs)

    return instconfig


def combine_params(instconfig: str) -> dict[str, str | int]:
    """Query parameters of the /combine endpoint, for a StationXML response

    The labels and the place of the channels are set by nrlx afterwards, so the
    request asks only the response; a missing response is a 404 error instead of an
    empty answer.

    Args:
        instconfig: instconfig of the response, see cascade_instconfig.

    Returns:
        query parameters, by name.


    """
    params: dict[str, str | int] = {
        "instconfig": instconfig,
        "format": "stationxml",
        "nodata": 404,
    }

    return params


def is_voltage(units: str | None) -> bool:
    """Whether units are a voltage

    Args:
        units: units of a stage, None or empty when missing.

    Returns:
        True for V, mV, uV or nV, in any case.


    """
    voltage = (units or "").upper() in VOLTAGES

    return voltage


def sensor_stages(response: Response) -> list[ResponseStage]:
    """Stages of the sensor in a response: up to the first with a voltage output

    A response without stages but with a polynomial (the polynomial sensors of the
    NRL) gives its polynomial as the only stage.

    Args:
        response: response of a sensor, or of a whole channel.

    Returns:
        copies of the stages of the sensor.

    Raises:
        ValueError: if no stage has a voltage output.


    """
    stages = list(response.response_stages)
    polynomial = response.instrument_polynomial
    if not stages and polynomial is not None:
        stages = [
            PolynomialResponseStage(
                1,
                None,
                None,
                polynomial.input_units,
                polynomial.output_units,
                polynomial.frequency_lower_bound,
                polynomial.frequency_upper_bound,
                polynomial.approximation_lower_bound,
                polynomial.approximation_upper_bound,
                polynomial.maximum_error,
                polynomial.coefficients,
                approximation_type=polynomial.approximation_type,
                input_units_description=polynomial.input_units_description,
                output_units_description=polynomial.output_units_description,
            )
        ]
    ends = [
        number for number, stage in enumerate(stages) if is_voltage(stage.output_units)
    ]
    match ends:
        case [end, *_]:
            kept = [copy.deepcopy(stage) for stage in stages[: end + 1]]
        case _:
            outputs = ", ".join(str(stage.output_units) for stage in stages)
            raise ValueError(
                "The sensor response has no stage with a voltage output "
                f"(outputs: {outputs or 'no stages'})."
            )

    return kept


def datalogger_stages(response: Response) -> list[ResponseStage]:
    """Stages of the datalogger in a response: from the first with a voltage or an
    empty input

    Args:
        response: response of a datalogger, or of a whole channel.

    Returns:
        copies of the stages of the datalogger.

    Raises:
        ValueError: if no stage has a voltage or an empty input.


    """
    stages = list(response.response_stages)
    starts = [
        number
        for number, stage in enumerate(stages)
        if is_voltage(stage.input_units) or not stage.input_units
    ]
    match starts:
        case [start, *_]:
            kept = [copy.deepcopy(stage) for stage in stages[start:]]
        case _:
            inputs = ", ".join(str(stage.input_units) for stage in stages)
            raise ValueError(
                "The datalogger response has no stage with a voltage input "
                f"(inputs: {inputs or 'no stages'})."
            )

    return kept


def join_units(
    sensor: list[ResponseStage], datalogger: list[ResponseStage]
) -> list[str]:
    """Chain the units where the datalogger takes the output of the sensor, in place

    An empty unit takes the unit of the other side, as the NRL service does.

    Args:
        sensor: stages of the sensor, the last one gives the voltage.
        datalogger: stages of the datalogger, the first one takes it.

    Returns:
        the notes on the units filled.

    Raises:
        ValueError: if the two units differ.


    """
    last, first = sensor[-1], datalogger[0]
    notes = list()
    match (last.output_units or "", first.input_units or ""):
        case (given, "") if given:
            first.input_units = given
            first.input_units_description = last.output_units_description
            notes.append(f"datalogger stage 1: empty input unit set to {given}")
        case ("", taken) if taken:
            last.output_units = taken
            last.output_units_description = first.input_units_description
            notes.append(
                f"sensor stage {len(sensor)}: empty output unit set to {taken}"
            )
        case (given, taken) if given.upper() != taken.upper():
            raise ValueError(
                f"The units do not chain: the sensor gives {given}, the datalogger "
                f"takes {taken}."
            )
        case _:
            pass

    return notes


def normalize(stages: list[ResponseStage]) -> list[str]:
    """Correct the normalization factor of the poles and zeros stages, in place

    The normalization factor makes a stage worth exactly its gain at its
    normalization frequency; when it does not, the gain wins and the factor is
    recomputed (12 % of the NRL sensors need it).

    Args:
        stages: the stages, numbered.

    Returns:
        the notes on the factors corrected by more than NORMALIZATION_NOTED.


    """
    notes = list()
    for stage in stages:
        if isinstance(stage, PolesZerosResponseStage):
            frequency = float(stage.normalization_frequency)
            value = abs(transfer(stage, frequency))
            if value and abs(value - 1.0) > NORMALIZATION_TOLERANCE:
                stage.normalization_factor = float(stage.normalization_factor) / value
            if value and abs(value - 1.0) > NORMALIZATION_NOTED:
                notes.append(
                    f"stage {stage.stage_sequence_number}: normalization factor "
                    f"corrected by x{1.0 / value:.6g}, so that the stage is its gain "
                    f"{float(stage.stage_gain):g} at {frequency:g} Hz"
                )

    return notes


def output_rate(stages: list[ResponseStage]) -> float | None:
    """Sample rate at the output of the stages

    Args:
        stages: the stages.

    Returns:
        the output rate in samples per second, None without digital stages.


    """
    rates = [
        float(stage.decimation_input_sample_rate) / int(stage.decimation_factor)
        for stage in stages
        if stage.decimation_input_sample_rate and stage.decimation_factor
    ]
    rate = rates[-1] if rates else None

    return rate


def sensitivity_frequency(
    stages: list[ResponseStage], sensor: list[ResponseStage], rate: float | None
) -> tuple[float, list[str]]:
    """Frequency of the overall sensitivity: the sensor's, capped by the output rate

    Args:
        stages: the combined stages, the sensor first.
        sensor: the stages of the sensor, normalized.
        rate: output rate, None without digital stages.

    Returns:
        the frequency in Hz, and the notes when the cap applies: the cap, and the
        sensor out of its flat band at the capped frequency.


    """
    first = stages[0]
    frequency = float(
        (
            first.normalization_frequency
            if isinstance(first, PolesZerosResponseStage)
            else first.stage_gain_frequency
        )
        or 1.0
    )

    # the sensor's frequency can be above what the channel passes
    notes = list()
    if rate is not None and frequency > rate * MAX_RATE_FRACTION:
        capped = rate * MAX_RATE_FRACTION
        notes.append(
            f"sensitivity at {capped:g} Hz, a tenth of the {rate:g} sps output, "
            f"instead of the sensor's {frequency:g} Hz"
        )

        # the channel may see none of the sensor's flat band (a geophone on a slow
        # channel): any frequency it records is in the roll-off
        fraction = response_amplitude(sensor, capped) / response_amplitude(
            sensor, frequency
        )
        if fraction < FLAT_BAND_FRACTION:
            notes.append(
                f"the sensor gives {fraction * 100:.3g}% of its gain at {capped:g} "
                f"Hz: the {rate:g} sps channel sees none of its flat band"
            )
        frequency = capped

    return frequency, notes


def combine_responses(
    sensor: Response, datalogger: Response
) -> tuple[Response, list[str]]:
    """Response of a sensor followed by a datalogger, from any two responses

    The sensor stages go up to the voltage and the datalogger stages start there;
    the units are chained, the stages renumbered, the poles and zeros normalized to
    their gains, and the overall sensitivity computed from the stages. A
    polynomial sensor gives a polynomial instead, its coefficients divided by the
    powers of the gain of the datalogger.

    Args:
        sensor: response of the sensor, or of a whole channel.
        datalogger: response of the datalogger, or of a whole channel.

    Returns:
        the combined response, and the notes on what was filled or corrected.

    Raises:
        ValueError: if a response has no voltage boundary, the units do not chain,
            or a stage cannot be evaluated.


    """
    first = sensor_stages(sensor)
    second = datalogger_stages(datalogger)
    notes = join_units(first, second)
    stages = first + second
    for number, stage in enumerate(stages, start=1):
        stage.stage_sequence_number = number
    notes += normalize(stages)

    match stages[0]:
        case PolynomialResponseStage() as polynomial:
            # the counts back to the physical units: a_k / G^k
            gain = math.prod((float(stage.stage_gain) for stage in second), start=1.0)
            coefficients = [
                float(c) / gain**k for k, c in enumerate(polynomial.coefficients)
            ]
            combined = Response(
                instrument_polynomial=InstrumentPolynomial(
                    polynomial.input_units,
                    stages[-1].output_units,
                    polynomial.frequency_lower_bound,
                    polynomial.frequency_upper_bound,
                    polynomial.approximation_lower_bound,
                    polynomial.approximation_upper_bound,
                    polynomial.maximum_error,
                    coefficients,
                    approximation_type=polynomial.approximation_type,
                    input_units_description=polynomial.input_units_description,
                    output_units_description=stages[-1].output_units_description,
                ),
                response_stages=stages,
            )
        case _:
            frequency, capped = sensitivity_frequency(
                stages, first, output_rate(stages)
            )
            notes += capped
            combined = Response(
                instrument_sensitivity=InstrumentSensitivity(
                    response_amplitude(stages, frequency),
                    frequency,
                    stages[0].input_units,
                    stages[-1].output_units,
                    input_units_description=stages[0].input_units_description,
                    output_units_description=stages[-1].output_units_description,
                ),
                response_stages=stages,
            )

    return combined, notes


def received_notes(response: Response) -> list[str]:
    """Notes on a response kept as the NRL gives it: normalization factors that
    contradict their gains, and a stated sensitivity that its stages do not give

    Args:
        response: response of the service, or of a file of the local copy.

    Returns:
        the notes, empty when the response is consistent.


    """
    notes = list()

    # each poles and zeros stage worth its gain at its normalization frequency
    for stage in response.response_stages:
        if isinstance(stage, PolesZerosResponseStage):
            frequency = float(stage.normalization_frequency)
            value = abs(transfer(stage, frequency))
            if value and abs(value - 1.0) > NORMALIZATION_NOTED:
                notes.append(
                    f"stage {stage.stage_sequence_number}: the normalization factor "
                    f"gives x{value:.6g} of its gain {float(stage.stage_gain):g} at "
                    f"{frequency:g} Hz, kept as received (obspy lets the gain win "
                    f"unless the sensitivity is at {frequency:g} Hz); a combination "
                    "by nrlx corrects it"
                )

    # the stated sensitivity against the one of the stages
    sensitivity = response.instrument_sensitivity
    computed = None
    if sensitivity is not None and response.response_stages:
        try:
            computed = response_amplitude(
                response.response_stages, float(sensitivity.frequency)
            )
        except ValueError as err:
            notes.append(f"the sensitivity cannot be checked: {err}")
    if sensitivity is not None and computed:
        ratio = float(sensitivity.value) / computed
        if abs(ratio - 1.0) > SENSITIVITY_NOTED:
            notes.append(
                f"the stated sensitivity {float(sensitivity.value):g} at "
                f"{float(sensitivity.frequency):g} Hz is x{ratio:.4g} what the stages "
                f"give ({computed:.6g}): remove_response uses the stages, "
                "remove_sensitivity the stated value; a combination by nrlx "
                "recomputes it"
            )

    return notes
