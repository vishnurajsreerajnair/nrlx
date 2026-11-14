from __future__ import annotations

from nrlx.core.combine import cascade_instconfig, combine_params


def test_cascade_joins_sensor_and_datalogger_with_a_colon():
    assert cascade_instconfig("sensor_A", "datalogger_B") == "sensor_A:datalogger_B"


def test_cascade_without_datalogger_is_the_sensor():
    assert cascade_instconfig("sensor_A", None) == "sensor_A"


def test_params_without_codes():
    params = combine_params(
        "sensor_A", "stationxml", False, None, None, None, None, None, None
    )

    assert params == {"instconfig": "sensor_A", "format": "stationxml", "nodata": 404}


def test_params_zip_suffix():
    params = combine_params(
        "sensor_A", "resp", True, None, None, None, None, None, None
    )

    assert params["format"] == "resp.zip"


def test_params_codes_only_when_given():
    params = combine_params(
        "sensor_A",
        "stationxml",
        False,
        "XX",
        "YY",
        "00",
        "ZZZ",
        "2021-01-01",
        None,
    )

    assert params["network"] == "XX"
    assert params["station"] == "YY"
    assert params["location"] == "00"
    assert params["channel"] == "ZZZ"
    assert params["starttime"] == "2021-01-01"
    assert "endtime" not in params
