from __future__ import annotations

import pytest

from nrlx.models.build import Build
from nrlx.models.instrument import Instrument


def test_defaults():
    request = Build(sensor=Instrument(instconfig="sensor_A"))

    assert request.datalogger is None
    assert request.format == "stationxml"
    assert not request.compress
    assert request.channels == []
    assert not request.merge_channels
    assert request.latitude is None
    assert request.longitude is None
    assert request.elevation == 0.0
    assert request.depth == 0.0


def test_repeated_channels_are_rejected():
    with pytest.raises(ValueError, match=r"unique. Repeated \['HHZ'\]"):
        Build(sensor=Instrument(instconfig="sensor_A"), channels=["HHZ", "HHN", "HHZ"])


@pytest.mark.parametrize("channels", [[], ["HHZ"]])
def test_merge_needs_two_channels(channels):
    with pytest.raises(ValueError, match="at least two channels"):
        Build(
            sensor=Instrument(instconfig="sensor_A"),
            channels=channels,
            merge_channels=True,
        )


@pytest.mark.parametrize(
    "format, compress",
    [("resp", False), ("stationxml-resp", False), ("stationxml", True)],
)
def test_merge_needs_uncompressed_stationxml(format, compress):
    with pytest.raises(ValueError, match="stationxml format, not zipped"):
        Build(
            sensor=Instrument(instconfig="sensor_A"),
            format=format,
            compress=compress,
            channels=["HHZ", "HHN"],
            merge_channels=True,
        )


@pytest.mark.parametrize("latitude, longitude", [(49.0, None), (None, 8.0)])
def test_latitude_and_longitude_go_together(latitude, longitude):
    with pytest.raises(ValueError, match="go together"):
        Build(
            sensor=Instrument(instconfig="sensor_A"),
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize("elevation, depth", [(112.0, 0.0), (0.0, 25.0)])
def test_elevation_and_depth_need_the_coordinates(elevation, depth):
    with pytest.raises(ValueError, match="need the latitude and the longitude"):
        Build(
            sensor=Instrument(instconfig="sensor_A"),
            elevation=elevation,
            depth=depth,
        )


@pytest.mark.parametrize(
    "latitude, longitude, depth, message",
    [
        (91.0, 8.0, 0.0, "latitude must be within"),
        (49.0, -181.0, 0.0, "longitude must be within"),
        (49.0, 8.0, -1.0, "depth must not be negative"),
    ],
)
def test_coordinates_out_of_range_are_rejected(latitude, longitude, depth, message):
    with pytest.raises(ValueError, match=message):
        Build(
            sensor=Instrument(instconfig="sensor_A"),
            latitude=latitude,
            longitude=longitude,
            depth=depth,
        )


@pytest.mark.parametrize(
    "format, compress",
    [("resp", False), ("stationxml-resp", False), ("stationxml", True)],
)
def test_coordinates_need_uncompressed_stationxml(format, compress):
    with pytest.raises(ValueError, match="coordinates need the stationxml format"):
        Build(
            sensor=Instrument(instconfig="sensor_A"),
            format=format,
            compress=compress,
            latitude=49.0,
            longitude=8.0,
        )
