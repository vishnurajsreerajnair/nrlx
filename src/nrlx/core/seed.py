"""SEED conventions of the channel codes, for the notes on the channels given"""

from __future__ import annotations


def band_codes(sample_rate: float) -> list[str]:
    """Band codes that the SEED norm gives to a sample rate

    The first letter of a channel code is its band: for example H or E from 80 to
    250 sps, B or S from 10 to 80 sps (the letter depends on the corner period of
    the sensor, which is not checked). SEED manual, appendix A.

    Args:
        sample_rate: sample rate of the channel in samples per second.

    Returns:
        the band codes of the rate; empty when the norm has no band for it here
        (from 5000 sps, or below 0.001 sps).


    """
    if 1000.0 <= sample_rate < 5000.0:
        codes = ["F", "G"]
    elif 250.0 <= sample_rate < 1000.0:
        codes = ["C", "D"]
    elif 80.0 <= sample_rate < 250.0:
        codes = ["H", "E"]
    elif 10.0 <= sample_rate < 80.0:
        codes = ["B", "S"]
    elif 1.0 < sample_rate < 10.0:
        codes = ["M"]
    elif 0.5 <= sample_rate <= 1.0:
        codes = ["L"]
    elif 0.05 <= sample_rate < 0.5:
        codes = ["V"]
    elif 0.001 <= sample_rate < 0.05:
        codes = ["U"]
    else:
        codes = []

    return codes
