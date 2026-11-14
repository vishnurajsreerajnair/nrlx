"""Amplitude of the response stages, computed directly instead of with evalresp

The rules are those of evalresp, so that a sensitivity computed here is the one obspy
deconvolves with.


"""

from __future__ import annotations

import cmath
import math

from obspy.core.inventory.response import (
    CoefficientsTypeResponseStage,
    FIRResponseStage,
    PolesZerosResponseStage,
    PolynomialResponseStage,
    ResponseListResponseStage,
    ResponseStage,
)

# a FIR whose coefficients sum this far from 1 is normalized by evalresp
FIR_TOLERANCE = 0.02


def transfer(stage: ResponseStage, frequency: float) -> complex:
    """Transfer function of a stage at a frequency, before its gain

    The poles and zeros are analog (Laplace in rad/s or in Hz) or digital (Z, at the
    input rate of the stage), with their normalization factor; the coefficients are
    a digital filter, numerator over denominator; a response list is interpolated;
    a stage with a gain only is 1.

    Args:
        stage: response stage.
        frequency: frequency in Hz.

    Returns:
        the complex value of the transfer function.

    Raises:
        ValueError: if a digital stage has no input sample rate, a response list
            does not reach the frequency, or the stage is a polynomial or of an
            unknown type.


    """
    match stage:
        case PolesZerosResponseStage():
            kind = str(stage.pz_transfer_function_type).upper()
            if "RADIANS" in kind:
                variable = complex(0.0, 2.0 * math.pi * frequency)
            elif "HERTZ" in kind:
                variable = complex(0.0, frequency)
            else:
                angle = 2.0 * math.pi * frequency / input_rate(stage)
                variable = cmath.exp(complex(0.0, angle))
            numerator = math.prod(
                (variable - complex(zero) for zero in stage.zeros), start=complex(1.0)
            )
            denominator = math.prod(
                (variable - complex(pole) for pole in stage.poles), start=complex(1.0)
            )
            value = float(stage.normalization_factor) * numerator / denominator
        case CoefficientsTypeResponseStage() | FIRResponseStage():
            angle = -2.0 * math.pi * frequency / input_rate(stage)
            delay = cmath.exp(complex(0.0, angle))
            value = polynomial(numerator_coefficients(stage), delay) / polynomial(
                denominator_coefficients(stage), delay
            )
        case ResponseListResponseStage():
            value = complex(listed_amplitude(stage, frequency))
        case PolynomialResponseStage():
            raise ValueError("A polynomial stage has no transfer function.")
        case ResponseStage() if type(stage) is ResponseStage:
            value = complex(1.0)
        case _:
            raise ValueError(f"Unknown stage type {type(stage).__name__}.")

    return value


def numerator_coefficients(
    stage: CoefficientsTypeResponseStage | FIRResponseStage,
) -> list[float]:
    """Numerator of a digital filter, the symmetric halves of a FIR unfolded

    Args:
        stage: coefficients or FIR stage.

    Returns:
        the coefficients, first to last; [1.0] for a stage without any.


    """
    match stage:
        case FIRResponseStage(symmetry="EVEN"):
            half = [float(c) for c in stage.coefficients]
            coefficients = half + half[::-1]
        case FIRResponseStage(symmetry="ODD"):
            half = [float(c) for c in stage.coefficients]
            coefficients = half + half[-2::-1]
        case FIRResponseStage():
            coefficients = [float(c) for c in stage.coefficients]
        case _:
            coefficients = [float(c) for c in stage.numerator]

    return coefficients or [1.0]


def denominator_coefficients(
    stage: CoefficientsTypeResponseStage | FIRResponseStage,
) -> list[float]:
    """Denominator of a digital filter

    Args:
        stage: coefficients or FIR stage.

    Returns:
        the coefficients, first to last; [1.0] for a FIR.


    """
    coefficients = (
        [float(c) for c in stage.denominator]
        if isinstance(stage, CoefficientsTypeResponseStage)
        else []
    )

    return coefficients or [1.0]


def polynomial(coefficients: list[float], variable: complex) -> complex:
    """Value of the polynomial sum c_k x^k

    Args:
        coefficients: c_0 first.
        variable: x.

    Returns:
        the value.


    """
    value = sum(
        (c * variable**k for k, c in enumerate(coefficients)), start=complex(0.0)
    )

    return value


def listed_amplitude(stage: ResponseListResponseStage, frequency: float) -> float:
    """Amplitude of a response list at a frequency, interpolated linearly as evalresp
    does

    Args:
        stage: response list stage.
        frequency: frequency in Hz, inside the list.

    Returns:
        the amplitude.

    Raises:
        ValueError: if the frequency is outside the list.


    """
    points = sorted(
        (float(element.frequency), float(element.amplitude))
        for element in stage.response_list_elements
    )
    around = [
        (low, high)
        for low, high in zip(points, points[1:], strict=False)
        if low[0] <= frequency <= high[0]
    ]
    match around:
        case [((low, below), (high, above)), *_] if high > low:
            amplitude = below + (above - below) * (frequency - low) / (high - low)
        case [((_, below), _), *_]:
            amplitude = below
        case _:
            raise ValueError(
                f"{frequency:g} Hz is outside the response list "
                f"({points[0][0]:g} to {points[-1][0]:g} Hz)."
            )

    return amplitude


def stage_amplitude(
    stage: ResponseStage, frequency: float, sensitivity_frequency: float
) -> float:
    """Amplitude of a stage at a frequency, as evalresp computes it in a channel
    whose overall sensitivity is at sensitivity_frequency

    The rules of evalresp (norm_resp and check_sym): a stage whose gain frequency
    (and, for the poles and zeros, normalization frequency) is not the sensitivity
    frequency is renormalized, its shape scaled to its gain at its gain frequency,
    so the gain wins; otherwise it is used as written, with its normalization
    factor, except a FIR of coefficients whose sum is more than 2 % from 1, divided
    by that sum.

    Args:
        stage: response stage.
        frequency: frequency in Hz.
        sensitivity_frequency: frequency of the overall sensitivity of the channel.

    Returns:
        the amplitude, signed as the gain.

    Raises:
        ValueError: see transfer.


    """
    value = abs(transfer(stage, frequency))
    gain = float(stage.stage_gain)
    references = [float(stage.stage_gain_frequency or 0.0)]
    if isinstance(stage, PolesZerosResponseStage):
        references.append(float(stage.normalization_frequency))
    filtering = isinstance(
        stage,
        PolesZerosResponseStage | CoefficientsTypeResponseStage | FIRResponseStage,
    )
    renormalized = filtering and any(
        reference != sensitivity_frequency for reference in references
    )

    # the gain wins, or the stage as written
    if renormalized:
        at_gain = abs(transfer(stage, references[0]))
        amplitude = gain * value / at_gain if at_gain else gain * value
    else:
        amplitude = gain * value * fir_scale(stage)

    return amplitude


def fir_scale(stage: ResponseStage) -> float:
    """Scale evalresp applies to a FIR of coefficients that is not normalized

    Args:
        stage: response stage.

    Returns:
        1 / the sum of the coefficients when it is more than FIR_TOLERANCE from 1,
        else 1.


    """
    scale = 1.0
    if isinstance(stage, CoefficientsTypeResponseStage) and not stage.denominator:
        total = sum(numerator_coefficients(stage))
        if total and abs(total - 1.0) > FIR_TOLERANCE:
            scale = 1.0 / abs(total)

    return scale


def response_amplitude(stages: list[ResponseStage], frequency: float) -> float:
    """Amplitude of a cascade of stages at the frequency of its overall sensitivity:
    the sensitivity that evalresp agrees with

    Args:
        stages: the stages, in order.
        frequency: frequency of the sensitivity in Hz.

    Returns:
        the product of the amplitudes of the stages.

    Raises:
        ValueError: see transfer.


    """
    amplitude = math.prod(
        (stage_amplitude(stage, frequency, frequency) for stage in stages), start=1.0
    )

    return amplitude


def input_rate(stage: ResponseStage) -> float:
    """Input sample rate of a digital stage

    Args:
        stage: digital stage.

    Returns:
        the rate in samples per second.

    Raises:
        ValueError: if the stage has none.


    """
    rate = stage.decimation_input_sample_rate
    if not rate:
        raise ValueError(
            f"Stage {stage.stage_sequence_number} is digital but has no input "
            "sample rate."
        )

    return float(rate)
