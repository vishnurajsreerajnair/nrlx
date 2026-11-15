"""What the end-to-end scripts share: the nrlx command, the curves and their
comparison, the errors a case records


"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import httpx
import numpy as np
import numpy.typing as npt
from obspy.core.inventory.response import Response
from obspy.io.xseed.utils import SEEDParserException

from nrlx.core.convert import check_frequencies

# the nrlx command of the environment that runs the script
NRLX = Path(sys.executable).with_name("nrlx")

# the errors a case records as its failure instead of stopping the run: those of
# nrlx (see its CLAUDE.md), of obspy's arithmetic and of its SEED parser
CASE_ERRORS = (
    ValueError,
    LookupError,
    OSError,
    ArithmeticError,
    httpx.HTTPError,
    SEEDParserException,
)


def run_nrlx(arguments: list[str], stdin: str | None = None) -> tuple[int, str]:
    """Run the nrlx command, with a wide terminal and no user environment

    Args:
        arguments: arguments after nrlx.
        stdin: text on its standard input, None for none.

    Returns:
        the exit code, and the standard output followed by the standard error.


    """
    done = subprocess.run(
        [str(NRLX), *arguments],
        capture_output=True,
        text=True,
        input=stdin,
        env={"COLUMNS": "250", "PATH": "/usr/bin"},
        check=False,
    )

    return done.returncode, f"{done.stdout}{done.stderr}"


def grid(sample_rate: float | None) -> npt.NDArray[np.float64]:
    """Frequencies of the comparisons, those nrlx checks a written file at

    Args:
        sample_rate: sample rate of the channel, None without digital stages.

    Returns:
        the frequencies in Hz.


    """
    frequencies = np.array(check_frequencies(sample_rate or None))

    return frequencies


def curve(
    response: Response, frequencies: npt.NDArray[np.float64], output: str = "DEF"
) -> npt.NDArray[np.float64]:
    """Amplitude of a response by obspy's evalresp

    Args:
        response: response with a sensitivity.
        frequencies: frequencies in Hz.
        output: DEF for the units of the response, DISP, VEL or ACC.

    Returns:
        the amplitude at each frequency.


    """
    values = response.get_evalresp_response_for_frequencies(frequencies, output=output)
    amplitudes: npt.NDArray[np.float64] = np.abs(values)

    return amplitudes


def deviation(
    reference: npt.NDArray[np.float64], other: npt.NDArray[np.float64]
) -> float:
    """Largest relative difference of two curves, where both are above zero

    Args:
        reference: the curve compared with.
        other: the curve compared.

    Returns:
        max |other / reference - 1|, 0 when no point is above zero in both.


    """
    mask = (reference > 0) & (other > 0)
    largest = (
        float(np.max(np.abs(other[mask] / reference[mask] - 1.0)))
        if mask.any()
        else 0.0
    )

    return largest
