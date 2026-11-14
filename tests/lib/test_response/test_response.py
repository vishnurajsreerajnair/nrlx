from __future__ import annotations

import pytest

from nrlx.models.response import BuiltResponse


def test_save_creates_the_folders(tmp_path):
    response = BuiltResponse(b"payload", "stationxml", "sensor_A")
    output_file = tmp_path / "sub" / "response.xml"

    saved = response.save(str(output_file))

    assert saved == output_file
    assert output_file.read_bytes() == b"payload"


def test_conversions(make_stationxml):
    response = BuiltResponse(make_stationxml("EHZ"), "stationxml", "sensor_A")

    assert response.to_inventory()[0][0][0].code == "EHZ"
    assert response.to_response().instrument_sensitivity.value == 1500.0
    assert response.to_paz().stage_gain == 1500.0


@pytest.mark.parametrize(
    "format, compressed",
    [("resp", False), ("stationxml-resp", False), ("stationxml", True)],
)
def test_conversions_need_uncompressed_stationxml(format, compressed):
    response = BuiltResponse(b"payload", format, "sensor_A", compressed)

    with pytest.raises(ValueError, match="needs an uncompressed stationxml"):
        response.to_response()
