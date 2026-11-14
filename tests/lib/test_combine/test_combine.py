from __future__ import annotations

from nrlx.core.combine import cascade_instconfig, combine_params


def test_cascade_joins_the_parts_with_a_colon():
    assert cascade_instconfig(["sensor_A", "datalogger_B"]) == "sensor_A:datalogger_B"


def test_cascade_of_a_single_part_is_the_part():
    assert cascade_instconfig(["integrated_C"]) == "integrated_C"


def test_params_ask_the_stationxml_without_labels():
    assert combine_params("sensor_A") == {
        "instconfig": "sensor_A",
        "format": "stationxml",
        "nodata": 404,
    }
