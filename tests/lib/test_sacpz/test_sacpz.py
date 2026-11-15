from __future__ import annotations

import warnings

import obspy
import pytest

from nrlx.io.sacpz import read_sacpz


def test_read_sacpz_reads_what_obspy_writes(station_xml, tmp_path):
    inventory = obspy.read_inventory(str(station_xml))
    path = tmp_path / "station.pz"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        inventory.write(str(path), format="SACPZ")

    channels = read_sacpz(path.read_text())

    assert [seedid for seedid, *_ in channels] == [
        "XY.T13.00.HHZ",
        "XY.T13.00.HHN",
        "XY.T13.00.HHE",
    ]
    _, zeros, poles, constant, rate = channels[0]
    stage = inventory[0][0][0].response.response_stages[0]
    # one more zero at the origin, from m/s to m
    assert zeros == pytest.approx([*stage.zeros, 0j], rel=1e-6)
    assert poles == pytest.approx(stage.poles, rel=1e-6)
    sensitivity = inventory[0][0][0].response.instrument_sensitivity.value
    assert constant == pytest.approx(stage.normalization_factor * sensitivity, rel=1e-6)
    assert rate == inventory[0][0][0].sample_rate


def test_read_sacpz_puts_the_values_not_listed_at_the_origin():
    text = "* NETWORK : XY\nZEROS 3\n-1.0 0.0\nPOLES 1\n-2.0 0.0\nCONSTANT 5.0\n"

    [(seedid, zeros, poles, constant, rate)] = read_sacpz(text)

    assert seedid == "XY..."
    assert zeros == [-1 + 0j, 0j, 0j]
    assert poles == [-2 + 0j]
    assert constant == 5.0
    # no SAMPLE RATE comment
    assert rate is None


def test_read_sacpz_gives_the_sample_rate_of_each_block():
    text = (
        "* CHANNEL : HHZ\n* SAMPLE RATE : 100.0\nZEROS 0\nPOLES 0\nCONSTANT 1.0\n"
        "* CHANNEL : LHZ\nZEROS 0\nPOLES 0\nCONSTANT 1.0\n"
        "* CHANNEL : VHZ\n* SAMPLE RATE : None\nZEROS 0\nPOLES 0\nCONSTANT 1.0\n"
    )

    assert [rate for *_, rate in read_sacpz(text)] == [100.0, None, None]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("ZEROS 1\n0.0 0.0\n0.0 0.0\n", "Line 3: more zeros than the 1 announced."),
        ("ZEROS 0\nhello\n", "Line 2 is not SACPZ: hello"),
        ("ZEROS 0\nPOLES 0\n", "The last SACPZ block has no CONSTANT."),
    ],
)
def test_read_sacpz_refuses_a_malformed_block(text, message):
    with pytest.raises(ValueError, match=message):
        read_sacpz(text)
