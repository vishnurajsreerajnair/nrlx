"""Conversion of responses between formats: the format of a file, and the
amplitudes that check a file read back


"""

from __future__ import annotations

import math

from nrlx.schema.response import ResponseFormat

# a lossless format reads back within this relative difference
LOSSLESS_TOLERANCE = 1e-9

# the frequencies of a check: from LOWEST_FREQUENCY to this fraction of the rate
TOP_RATE_FRACTION = 0.4
LOWEST_FREQUENCY = 0.01
CHECK_POINTS = 60

# the top of the check without a sample rate, in Hz
TOP_WITHOUT_RATE = 50.0


def output_format(suffix: str) -> ResponseFormat:
    """Format of a response file from its extension

    Args:
        suffix: extension of the file, with its dot.

    Returns:
        stationxml for .xml, resp for .resp, sacpz for .pz or .sacpz.

    Raises:
        ValueError: for any other extension.


    """
    match suffix.lower():
        case ".xml":
            fileformat: ResponseFormat = "stationxml"
        case ".resp":
            fileformat = "resp"
        case ".pz" | ".sacpz":
            fileformat = "sacpz"
        case other:
            raise ValueError(
                f"Cannot tell the format from {other or 'no extension'}: use .xml, "
                ".resp or .pz, or --format."
            )

    return fileformat


def check_frequencies(rate: float | None) -> list[float]:
    """Frequencies at which a file read back is compared, log-spaced

    Args:
        rate: sample rate of the channel, None without digital stages.

    Returns:
        CHECK_POINTS frequencies in Hz, from LOWEST_FREQUENCY (or a hundredth of
        the top for a very slow channel) to TOP_RATE_FRACTION of the rate.


    """
    top = TOP_RATE_FRACTION * rate if rate else TOP_WITHOUT_RATE
    low = min(LOWEST_FREQUENCY, top / 100.0)
    step = (math.log10(top) - math.log10(low)) / (CHECK_POINTS - 1)
    frequencies = [10 ** (math.log10(low) + k * step) for k in range(CHECK_POINTS)]

    return frequencies


def pz_amplitude(
    zeros: list[complex], poles: list[complex], constant: float, frequency: float
) -> float:
    """Amplitude of poles and zeros in rad/s with a constant, as SACPZ writes them

    Args:
        zeros: zeros in rad/s.
        poles: poles in rad/s.
        constant: the constant, normalization and gain together.
        frequency: frequency in Hz.

    Returns:
        |constant x prod(s - z) / prod(s - p)| at s = 2 pi i f.


    """
    variable = complex(0.0, 2.0 * math.pi * frequency)
    numerator = math.prod((variable - zero for zero in zeros), start=complex(1.0))
    denominator = math.prod((variable - pole for pole in poles), start=complex(1.0))
    amplitude = abs(constant * numerator / denominator)

    return amplitude


def relative_difference(before: list[float], after: list[float]) -> float:
    """Largest relative difference between two curves, where both are positive

    Args:
        before: amplitudes of the reference.
        after: amplitudes compared, at the same frequencies.

    Returns:
        the largest |after / before - 1|, 0 when no point is positive in both.


    """
    differences = [
        abs(b / a - 1.0) for a, b in zip(before, after, strict=True) if a > 0 and b > 0
    ]
    difference = max(differences, default=0.0)

    return difference
