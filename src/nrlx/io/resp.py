"""RESP writer: the responses of an obspy Inventory as the RESP text of evalresp

Each channel is a header (blockettes 50 and 52) and its stages, one after the other:
poles and zeros (53), coefficients (54), response list (55), FIR (61) or polynomial
(62), each with its decimation (57) and its gain (58); then the sensitivity of the
channel as stage 0 (58), or its polynomial (62). The layout follows the RESP of the
NRL service, which obspy and evalresp read.


"""

from __future__ import annotations

from obspy import Inventory, UTCDateTime
from obspy.core.inventory import Channel
from obspy.core.inventory.response import (
    CoefficientsTypeResponseStage,
    FIRResponseStage,
    InstrumentPolynomial,
    PolesZerosResponseStage,
    PolynomialResponseStage,
    ResponseListResponseStage,
    ResponseStage,
)
from obspy.core.util.obspy_types import ComplexWithUncertainties

# significant digits after the point of the numbers: 16 digits give back the same
# float, where the NRL service writes 6 (+1.50000E+03)
DIGITS = 15

# width of the label column of the field lines, as in the RESP of the NRL service
LABEL_WIDTH = 39

# width of the inside of the boxes heading each blockette
BOX_WIDTH = 35


def write_resp(inventory: Inventory) -> str:
    """RESP text of every channel of an inventory, one after the other

    Args:
        inventory: inventory with the responses of its channels.

    Returns:
        the RESP text.

    Raises:
        ValueError: if a channel has no response, or a stage of an unknown type.


    """
    lines = [
        line
        for network in inventory
        for station in network
        for channel in station
        for line in channel_lines(network.code, station.code, channel)
    ]
    text = "".join(f"{line}\n" for line in lines)

    return text


def channel_lines(network: str, station: str, channel: Channel) -> list[str]:
    """RESP lines of a channel: its header, its stages and its sensitivity

    Args:
        network: network code.
        station: station code.
        channel: channel with its response.

    Returns:
        the lines, without line ends.

    Raises:
        ValueError: if the channel has no response, or a stage of an unknown type.


    """
    if channel.response is None:
        raise ValueError(
            f"Channel {network}.{station}.{channel.location_code}.{channel.code} "
            "has no response"
        )
    response = channel.response
    start = resp_time(channel.start_date)
    end = resp_time(channel.end_date)
    codes = (network, station, channel.location_code or "??", channel.code)

    # the header of the channel
    lines = [
        "#",
        "#" * 83,
        "#",
        field("B050F03", "Station:", station, 13),
        field("B050F16", "Network:", network, 13),
        field("B052F03", "Location:", channel.location_code or "??", 13),
        field("B052F04", "Channel:", channel.code, 13),
        field("B052F22", "Start date:", start, 13),
        field("B052F23", "End date:", end, 13),
    ]

    # each stage, its decimation and its gain
    for stage in response.response_stages:
        match stage:
            case PolesZerosResponseStage():
                lines += box("Response (Poles and Zeros)", codes, start, end)
                lines += poles_zeros_lines(stage)
            case CoefficientsTypeResponseStage():
                lines += box("Response (Coefficients)", codes, start, end)
                lines += coefficients_lines(stage)
            case ResponseListResponseStage():
                lines += box("Response List", codes, start, end)
                lines += response_list_lines(stage)
            case FIRResponseStage():
                lines += box("FIR Response", codes, start, end)
                lines += fir_lines(stage)
            case PolynomialResponseStage():
                lines += box("Response (Polynomial)", codes, start, end)
                lines += polynomial_lines(stage, stage.stage_sequence_number)
            case ResponseStage() if type(stage) is ResponseStage:
                pass
            case _:
                raise ValueError(
                    f"Stage {stage.stage_sequence_number} of {codes}: unknown "
                    f"type {type(stage).__name__}"
                )
        if stage.decimation_input_sample_rate is not None:
            lines += box("Decimation", codes, start, end)
            lines += decimation_lines(stage)
        # the gain of the stage; a stage without gain has none, as a gain of 0
        # makes evalresp refuse the file
        if (
            not isinstance(stage, PolynomialResponseStage)
            and stage.stage_gain is not None
        ):
            lines += box("Channel Sensitivity/Gain", codes, start, end)
            lines += gain_lines(
                stage.stage_sequence_number,
                stage.stage_gain,
                stage.stage_gain_frequency or 0.0,
            )

    # the sensitivity of the channel, stage 0, or its polynomial; a sensitivity
    # without value is left out
    if response.instrument_polynomial is not None:
        lines += box("Response (Polynomial)", codes, start, end)
        lines += polynomial_lines(response.instrument_polynomial, 0)
    elif (
        response.instrument_sensitivity is not None
        and response.instrument_sensitivity.value is not None
    ):
        sensitivity = response.instrument_sensitivity
        lines += box("Channel Sensitivity/Gain", codes, start, end)
        lines += gain_lines(0, sensitivity.value, sensitivity.frequency or 0.0)

    return lines


def poles_zeros_lines(stage: PolesZerosResponseStage) -> list[str]:
    """Blockette 53 of a poles and zeros stage

    Args:
        stage: poles and zeros stage.

    Returns:
        the lines.

    Raises:
        ValueError: if the transfer function type is unknown.


    """
    match stage.pz_transfer_function_type:
        case "LAPLACE (RADIANS/SECOND)":
            kind = "A - Laplace transform analog response, in rad/sec"
        case "LAPLACE (HERTZ)":
            kind = "B - Analog response, in Hz"
        case "LAPLACE (Z-TRANSFORM)" | "DIGITAL (Z-TRANSFORM)":
            kind = "D - Digital (Z-transform)"
        case other:
            raise ValueError(f"Unknown poles and zeros transfer function {other!r}")

    lines = [
        field("B053F03", "Transfer function type:", kind),
        field("B053F04", "Stage sequence number:", str(stage.stage_sequence_number)),
        field("B053F05", "Response in units lookup:", units(stage, "input")),
        field("B053F06", "Response out units lookup:", units(stage, "output")),
        field(
            "B053F07", "A0 normalization factor:", number(stage.normalization_factor)
        ),
        field(
            "B053F08",
            "Normalization frequency:",
            number(stage.normalization_frequency),
        ),
        field("B053F09", "Number of zeroes:", str(len(stage.zeros))),
        field("B053F14", "Number of poles:", str(len(stage.poles))),
    ]

    # the zeros, then the poles, with their errors
    if stage.zeros:
        lines += [
            "#              Complex zeroes:",
            "#              i  real          imag          real_error    imag_error",
        ]
        lines += [
            complex_line("B053F10-13", index, value)
            for index, value in enumerate(stage.zeros)
        ]
    if stage.poles:
        lines += [
            "#              Complex poles:",
            "#              i  real          imag          real_error    imag_error",
        ]
        lines += [
            complex_line("B053F15-18", index, value)
            for index, value in enumerate(stage.poles)
        ]

    return lines


def coefficients_lines(stage: CoefficientsTypeResponseStage) -> list[str]:
    """Blockette 54 of a coefficients stage

    Args:
        stage: coefficients stage.

    Returns:
        the lines.

    Raises:
        ValueError: if the transfer function type is unknown.


    """
    match stage.cf_transfer_function_type:
        case "ANALOG (RADIANS/SECOND)":
            kind = "A"
        case "ANALOG (HERTZ)":
            kind = "B"
        case "DIGITAL":
            kind = "D"
        case other:
            raise ValueError(f"Unknown coefficients transfer function {other!r}")

    lines = [
        field("B054F03", "Transfer function type:", kind),
        field("B054F04", "Stage sequence number:", str(stage.stage_sequence_number)),
        field("B054F05", "Response in units lookup:", units(stage, "input")),
        field("B054F06", "Response out units lookup:", units(stage, "output")),
        field("B054F07", "Number of numerators:", str(len(stage.numerator))),
        field("B054F10", "Number of denominators:", str(len(stage.denominator))),
    ]

    # the numerators, then the denominators, with their errors
    if stage.numerator:
        lines += [
            "#              Numerator coefficients:",
            "#              i  coefficient   error",
        ]
        lines += [
            f"B054F08-09  {index:4d}  {number(value)}  {number(error(value))}"
            for index, value in enumerate(stage.numerator)
        ]
    if stage.denominator:
        lines += [
            "#              Denominator coefficients:",
            "#              i  coefficient   error",
        ]
        lines += [
            f"B054F11-12  {index:4d}  {number(value)}  {number(error(value))}"
            for index, value in enumerate(stage.denominator)
        ]

    return lines


def response_list_lines(stage: ResponseListResponseStage) -> list[str]:
    """Blockette 55 of a response list stage

    Args:
        stage: response list stage.

    Returns:
        the lines.


    """
    elements = stage.response_list_elements
    lines = [
        field("B055F03", "Stage sequence number:", str(stage.stage_sequence_number)),
        field("B055F04", "Response in units lookup:", units(stage, "input")),
        field("B055F05", "Response out units lookup:", units(stage, "output")),
        field("B055F06", "Number of responses:", str(len(elements))),
        "#              frequency  amplitude  amp error  phase  phase error",
    ]
    lines += [
        "B055F07-11  "
        f"{number(element.frequency)}  {number(element.amplitude)}  "
        f"{number(error(element.amplitude))}  {number(element.phase)}  "
        f"{number(error(element.phase))}"
        for element in elements
    ]

    return lines


def fir_lines(stage: FIRResponseStage) -> list[str]:
    """Blockette 61 of a FIR stage

    Args:
        stage: FIR stage.

    Returns:
        the lines.

    Raises:
        ValueError: if the symmetry is unknown.


    """
    match stage.symmetry:
        case "NONE":
            symmetry = "A"
        case "ODD":
            symmetry = "B"
        case "EVEN":
            symmetry = "C"
        case other:
            raise ValueError(f"Unknown FIR symmetry {other!r}")

    lines = [
        field("B061F03", "Stage sequence number:", str(stage.stage_sequence_number)),
        field("B061F05", "Symmetry type:", symmetry),
        field("B061F06", "Response in units lookup:", units(stage, "input")),
        field("B061F07", "Response out units lookup:", units(stage, "output")),
        field("B061F08", "Number of numerators:", str(len(stage.coefficients))),
        "#              i  coefficient",
    ]
    lines += [
        f"B061F09    {index:4d}  {number(value)}"
        for index, value in enumerate(stage.coefficients)
    ]

    return lines


def polynomial_lines(
    polynomial: PolynomialResponseStage | InstrumentPolynomial, sequence: int
) -> list[str]:
    """Blockette 62 of a polynomial stage, or of the polynomial of the channel

    Args:
        polynomial: polynomial stage, or polynomial of the channel.
        sequence: stage sequence number, 0 for the channel.

    Returns:
        the lines.


    """
    lines = [
        field("B062F03", "Transfer function type:", "P"),
        field("B062F04", "Stage sequence number:", str(sequence)),
        field("B062F05", "Response in units lookup:", units(polynomial, "input")),
        field("B062F06", "Response out units lookup:", units(polynomial, "output")),
        field("B062F07", "Polynomial Approximation Type:", "M"),
        field("B062F08", "Valid Frequency Units:", "B"),
        field(
            "B062F09",
            "Lower Valid Frequency Bound:",
            number(polynomial.frequency_lower_bound),
        ),
        field(
            "B062F10",
            "Upper Valid Frequency Bound:",
            number(polynomial.frequency_upper_bound),
        ),
        field(
            "B062F11",
            "Lower Bound of Approximation:",
            number(polynomial.approximation_lower_bound),
        ),
        field(
            "B062F12",
            "Upper Bound of Approximation:",
            number(polynomial.approximation_upper_bound),
        ),
        field("B062F13", "Maximum Absolute Error:", number(polynomial.maximum_error)),
        field("B062F14", "Number of Coefficients:", str(len(polynomial.coefficients))),
        "#              i, coefficient,  error",
    ]
    lines += [
        f"B062F15-16  {index:4d}  {number(value)}  {number(error(value))}"
        for index, value in enumerate(polynomial.coefficients)
    ]

    return lines


def decimation_lines(stage: ResponseStage) -> list[str]:
    """Blockette 57 of the decimation of a stage

    Args:
        stage: stage with a decimation.

    Returns:
        the lines.


    """
    lines = [
        field("B057F03", "Stage sequence number:", str(stage.stage_sequence_number)),
        field(
            "B057F04",
            "Input sample rate (HZ):",
            number(stage.decimation_input_sample_rate),
        ),
        field("B057F05", "Decimation factor:", f"{stage.decimation_factor:05d}"),
        field("B057F06", "Decimation offset:", f"{stage.decimation_offset or 0:05d}"),
        field(
            "B057F07",
            "Estimated delay (seconds):",
            number(stage.decimation_delay or 0.0),
        ),
        field(
            "B057F08",
            "Correction applied (seconds):",
            number(stage.decimation_correction or 0.0),
        ),
    ]

    return lines


def gain_lines(sequence: int, gain: float, frequency: float) -> list[str]:
    """Blockette 58 of the gain of a stage, or of the sensitivity of the channel

    Args:
        sequence: stage sequence number, 0 for the sensitivity of the channel.
        gain: gain of the stage, or sensitivity of the channel.
        frequency: frequency of the gain in Hz.

    Returns:
        the lines.


    """
    lines = [
        field("B058F03", "Stage sequence number:", str(sequence)),
        field("B058F04", "Sensitivity:", number(gain)),
        field("B058F05", "Frequency of sensitivity:", number(frequency)),
        field("B058F06", "Number of calibrations:", "0"),
    ]

    return lines


def box(
    title: str, codes: tuple[str, str, str, str], start: str, end: str
) -> list[str]:
    """Comment box heading a blockette, which also ends the previous one for obspy

    Args:
        title: kind of the blockette, for example Decimation.
        codes: network, station, location and channel codes.
        start: start of the channel, as in the header.
        end: end of the channel, as in the header.

    Returns:
        the comment lines.


    """
    network, station, location, channel = codes
    margin = "#" + " " * 18
    border = f"{margin}+{'-' * BOX_WIDTH}+"
    names = f"{network}  {station}  {location}  {channel}"
    validity = f"{start} to {end}"
    lines = [
        "#",
        border,
        f"{margin}|{title.center(BOX_WIDTH)}|",
        f"{margin}|{names.center(BOX_WIDTH)}|",
        f"{margin}|{validity.center(BOX_WIDTH)}|",
        border,
        "#",
    ]

    return lines


def field(code: str, label: str, value: str, width: int = LABEL_WIDTH) -> str:
    """A field line: the blockette and field code, its label and its value

    Args:
        code: blockette and field code, for example B053F07.
        label: label, ending with a colon.
        value: value, as written.
        width: width of the label column.

    Returns:
        the line.


    """
    line = f"{code}     {label.ljust(width)}{value}"

    return line


def complex_line(code: str, index: int, value: ComplexWithUncertainties) -> str:
    """A line of a pole or a zero: its index, real and imaginary parts and errors

    Args:
        code: blockette and fields code, B053F10-13 or B053F15-18.
        index: index of the pole or zero.
        value: the pole or zero, with its uncertainty.

    Returns:
        the line.


    """
    # the upper uncertainty is the error, 0 without one
    uncertainty = value.upper_uncertainty or 0j
    line = (
        f"{code}  {index:4d}  {number(value.real)}  {number(value.imag)}  "
        f"{number(uncertainty.real)}  {number(uncertainty.imag)}"
    )

    return line


def units(stage: ResponseStage | InstrumentPolynomial, side: str) -> str:
    """Units of a stage as a lookup: the name, then its description

    Args:
        stage: stage, or polynomial of the channel.
        side: input or output.

    Returns:
        the units, for example "m/s - Velocity in Meters Per Second".


    """
    match side:
        case "input":
            name, description = stage.input_units, stage.input_units_description
        case _:
            name, description = stage.output_units, stage.output_units_description
    lookup = f"{name} - {description}" if description else f"{name}"

    return lookup


def error(value: float) -> float:
    """Upper uncertainty of a coefficient, 0 without one

    Args:
        value: a float, or a FloatWithUncertainties.

    Returns:
        the uncertainty.


    """
    uncertainty = getattr(value, "upper_uncertainty", None)
    found = float(uncertainty) if uncertainty is not None else 0.0

    return found


def number(value: float) -> str:
    """A number in the exponent form of RESP, with its sign

    Args:
        value: the number.

    Returns:
        the number, for example +1.500000000000000E+03.


    """
    text = f"{float(value):+.{DIGITS}E}"

    return text


def resp_time(time: UTCDateTime | None) -> str:
    """A time as RESP writes it, year,day of year,time

    Args:
        time: the time, None for no end.

    Returns:
        the time, for example 1970,001,00:00:00, with the ten-thousandths of a
        second of SEED when the time has a fraction (1970,001,00:00:00.7490), or
        No Ending Time.


    """
    match time:
        case None:
            text = "No Ending Time"
        case _ if time.microsecond // 100:
            text = f"{time.strftime('%Y,%j,%H:%M:%S')}.{time.microsecond // 100:04d}"
        case _:
            text = time.strftime("%Y,%j,%H:%M:%S")

    return text
