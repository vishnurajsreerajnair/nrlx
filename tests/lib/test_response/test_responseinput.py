from __future__ import annotations

from datetime import datetime

import msgspec
import pytest

from nrlx.schema.response import ResponseInput


def test_defaults():
    request = ResponseInput(sensor=["STS-2"])

    assert request.datalogger is None
    assert request.channels == []
    assert (request.network, request.station, request.location) == (None, None, None)
    assert (request.latitude, request.elevation, request.depth) == (None, 0.0, 0.0)


@pytest.mark.parametrize(
    "parts",
    [
        {"sensor": ["a"]},
        {"datalogger": ["a"]},
        {"sensor": ["a"], "datalogger": ["b"]},
        {"integrated": ["a"]},
        {"soh": ["a"]},
    ],
)
def test_allowed_parts(parts):
    ResponseInput(**parts)


@pytest.mark.parametrize(
    ("parts", "message"),
    [
        ({}, "needs a part"),
        ({"sensor": ["a"], "integrated": ["b"]}, "go as a sensor"),
        ({"datalogger": ["a"], "soh": ["b"]}, "go as a sensor"),
        ({"integrated": ["a"], "soh": ["b"]}, "go as a sensor"),
        ({"sensor": []}, "must not be empty"),
    ],
)
def test_refused_parts(parts, message):
    with pytest.raises(ValueError, match=message):
        ResponseInput(**parts)


def test_repeated_channels_are_refused():
    with pytest.raises(ValueError, match="Repeated"):
        ResponseInput(sensor=["a"], channels=["HHZ", "HHN", "HHZ"])


def test_end_before_start_is_refused():
    with pytest.raises(ValueError, match="end time must be after"):
        ResponseInput(
            sensor=["a"], starttime=datetime(2026, 1, 1), endtime=datetime(2025, 1, 1)
        )


@pytest.mark.parametrize(
    ("coordinates", "message"),
    [
        ({"latitude": 45.0}, "go together"),
        ({"longitude": 9.0}, "go together"),
        ({"elevation": 100.0}, "need the latitude"),
        ({"depth": 5.0}, "need the latitude"),
        ({"latitude": 91.0, "longitude": 9.0}, "within ±90"),
        ({"latitude": 45.0, "longitude": 181.0}, "within ±180"),
        ({"latitude": 45.0, "longitude": 9.0, "depth": -1.0}, "not be negative"),
    ],
)
def test_refused_coordinates(coordinates, message):
    with pytest.raises(ValueError, match=message):
        ResponseInput(sensor=["a"], **coordinates)


def test_decoded_from_json_with_iso_times():
    request = msgspec.json.decode(
        b'{"sensor": ["STS-2"], "starttime": "2026-01-01T00:00:00"}',
        type=ResponseInput,
    )

    assert request.starttime == datetime(2026, 1, 1)


def test_unknown_fields_are_refused():
    with pytest.raises(msgspec.ValidationError, match="unknown field"):
        msgspec.json.decode(b'{"sensor": ["a"], "colour": "red"}', type=ResponseInput)
