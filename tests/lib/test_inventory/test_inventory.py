from __future__ import annotations

from nrlx.io.inventory import merge_stationxml, read_stationxml, set_coordinates


def test_merge_adds_the_channels_to_the_first_station(make_stationxml):
    merged = merge_stationxml(
        [make_stationxml("EHZ"), make_stationxml("EHN"), make_stationxml("EHE")]
    )

    inventory = read_stationxml(merged)
    assert len(inventory) == 1
    assert len(inventory[0]) == 1
    station = inventory[0][0]
    assert [channel.code for channel in station] == ["EHZ", "EHN", "EHE"]
    assert station.total_number_of_channels == 3
    assert station.selected_number_of_channels == 3


def test_set_coordinates_places_the_station_and_its_channels(make_stationxml):
    merged = merge_stationxml([make_stationxml("EHZ"), make_stationxml("EHN")])

    placed = set_coordinates(merged, 49.096, -8.432, 112.0, 25.0)

    station = read_stationxml(placed)[0][0]
    assert (station.latitude, station.longitude, station.elevation) == (
        49.096,
        -8.432,
        112.0,
    )
    assert [
        (channel.latitude, channel.longitude, channel.elevation, channel.depth)
        for channel in station
    ] == [(49.096, -8.432, 112.0, 25.0), (49.096, -8.432, 112.0, 25.0)]
