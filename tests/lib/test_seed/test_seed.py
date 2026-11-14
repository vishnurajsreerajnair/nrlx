from __future__ import annotations

import pytest

from nrlx.core.seed import band_codes


@pytest.mark.parametrize(
    ("sample_rate", "codes"),
    [
        (5000.0, []),
        (1000.0, ["F", "G"]),
        (500.0, ["C", "D"]),
        (250.0, ["C", "D"]),
        (100.0, ["H", "E"]),
        (80.0, ["H", "E"]),
        (40.0, ["B", "S"]),
        (10.0, ["B", "S"]),
        (5.0, ["M"]),
        (1.0, ["L"]),
        (0.1, ["V"]),
        (0.01, ["U"]),
        (0.0001, []),
    ],
)
def test_band_codes(sample_rate, codes):
    assert band_codes(sample_rate) == codes
