from __future__ import annotations

from datetime import datetime

from obspy import UTCDateTime

from nrlx.io.inventory import label_channels, read_stationxml, set_coordinates


def test_label_channels_copies_the_channel_for_each_code(make_stationxml):
    response = read_stationxml(make_stationxml("ZZZ"))

    labelled = label_channels(
        response,
        "XY",
        "TST",
        "10",
        ["HHZ", "hhn", "X1"],
        datetime(2026, 1, 1),
        datetime(2027, 1, 1),
    )

    [network] = labelled
    [station] = network
    assert (network.code, station.code) == ("XY", "TST")
    # the codes as given, even outside the SEED norm
    assert [channel.code for channel in station] == ["HHZ", "hhn", "X1"]
    assert {channel.location_code for channel in station} == {"10"}
    assert station.total_number_of_channels == 3
    assert [channel.start_date for channel in station] == [UTCDateTime(2026, 1, 1)] * 3
    assert [channel.end_date for channel in station] == [UTCDateTime(2027, 1, 1)] * 3
    assert station.start_date == UTCDateTime(2026, 1, 1)
    assert network.end_date == UTCDateTime(2027, 1, 1)
    # the same response on each channel, the service answer unchanged
    sensitivities = {
        channel.response.instrument_sensitivity.value for channel in station
    }
    assert sensitivities == {1500.0}
    assert [channel.code for channel in response[0][0]] == ["ZZZ"]


def test_label_channels_keeps_the_placeholders_not_given(make_stationxml):
    response = read_stationxml(make_stationxml("ZZZ"))

    labelled = label_channels(response, None, None, None, [], None, None)

    [network] = labelled
    [station] = network
    [channel] = station
    assert (network.code, station.code, channel.code) == ("XY", "MYSTN", "ZZZ")


def test_label_channels_allows_an_empty_location(make_stationxml):
    labelled = label_channels(
        read_stationxml(make_stationxml("ZZZ")), None, None, "", ["HHZ"], None, None
    )

    assert labelled[0][0][0].location_code == ""


def test_set_coordinates_places_the_station_and_its_channels(make_stationxml):
    response = label_channels(
        read_stationxml(make_stationxml("ZZZ")),
        None,
        None,
        None,
        ["EHZ", "EHN"],
        None,
        None,
    )

    placed = set_coordinates(response, 49.096, -8.432, 112.0, 25.0)

    station = placed[0][0]
    assert (station.latitude, station.longitude, station.elevation) == (
        49.096,
        -8.432,
        112.0,
    )
    assert [
        (channel.latitude, channel.longitude, channel.elevation, channel.depth)
        for channel in station
    ] == [(49.096, -8.432, 112.0, 25.0), (49.096, -8.432, 112.0, 25.0)]
    assert response[0][0].latitude == 0.0
