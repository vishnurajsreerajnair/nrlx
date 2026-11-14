from __future__ import annotations

from pathlib import Path

import pytest

from nrlx.core.convert import (
    CHECK_POINTS,
    check_frequencies,
    output_format,
    pz_amplitude,
    relative_difference,
)
from nrlx.io.inventory import read_part

DATA_DIR = Path(__file__).parents[2] / "data"


@pytest.mark.parametrize(
    ("suffix", "expected"),
    [
        (".xml", "stationxml"),
        (".XML", "stationxml"),
        (".resp", "resp"),
        (".pz", "sacpz"),
        (".sacpz", "sacpz"),
    ],
)
def test_output_format_from_the_extension(suffix, expected):
    assert output_format(suffix) == expected


@pytest.mark.parametrize(("suffix", "shown"), [(".txt", ".txt"), ("", "no extension")])
def test_output_format_unknown_extension(suffix, shown):
    with pytest.raises(ValueError, match=f"Cannot tell the format from {shown}"):
        output_format(suffix)


def test_check_frequencies_span_up_to_a_fraction_of_the_rate():
    frequencies = check_frequencies(100.0)

    assert len(frequencies) == CHECK_POINTS
    assert frequencies[0] == pytest.approx(0.01)
    assert frequencies[-1] == pytest.approx(40.0)
    assert frequencies == sorted(frequencies)


def test_check_frequencies_without_rate_and_for_a_slow_channel():
    assert check_frequencies(None)[-1] == pytest.approx(50.0)
    # a hundredth of the top when the top is below 1 Hz
    slow = check_frequencies(0.1)
    assert (slow[0], slow[-1]) == pytest.approx((0.0004, 0.04))


def test_pz_amplitude_gives_the_curve_of_obspy():
    response = read_part(DATA_DIR / "nrl_part_sts2.xml")
    [stage] = response.response_stages
    frequencies = [0.01, 0.1, 1.0, 10.0]

    amplitudes = [
        pz_amplitude(
            stage.zeros,
            stage.poles,
            stage.normalization_factor * stage.stage_gain,
            frequency,
        )
        for frequency in frequencies
    ]

    evalresp = response.get_evalresp_response_for_frequencies(frequencies, output="VEL")
    assert amplitudes == pytest.approx([abs(value) for value in evalresp], rel=1e-9)


def test_relative_difference_skips_the_points_not_positive_in_both():
    assert relative_difference([1.0, 2.0, 0.0], [1.1, 2.0, 5.0]) == pytest.approx(0.1)
    assert relative_difference([0.0], [1.0]) == 0.0
