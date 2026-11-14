from __future__ import annotations

from datetime import datetime
from pathlib import Path

import obspy
import pytest
from obspy import UTCDateTime

from nrlx.io.inventory import (
    label_channels,
    placeholder_inventory,
    read_part,
    read_stationxml,
    set_coordinates,
)

DATA_DIR = Path(__file__).parents[2] / "data"


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


def test_read_part_of_a_single_channel():
    expected = obspy.read_inventory(DATA_DIR / "nrl_sts2_q330.xml")[0][0][0].response

    response = read_part(DATA_DIR / "nrl_sts2_q330.xml")
    from_resp = read_part(DATA_DIR / "nrl_sts2_q330.resp")

    assert response == expected
    assert len(from_resp.response_stages) == len(expected.response_stages)


def test_read_part_picks_a_channel_by_its_seed_id(tmp_path, make_stationxml):
    path = tmp_path / "two.xml"
    inventory = read_stationxml(make_stationxml("HHZ"))
    inventory = label_channels(inventory, None, None, "00", ["HHZ", "HHN"], None, None)
    inventory[0][0][1].response.response_stages[0].stage_gain = 750.0
    inventory.write(str(path), format="STATIONXML")

    response = read_part(path, "XY.MYSTN.00.HHN")

    assert response.response_stages[0].stage_gain == 750.0
    with pytest.raises(LookupError, match="2 channels or epochs"):
        read_part(path)
    with pytest.raises(LookupError, match=r"No channel XY.MYSTN.00.BHZ .*HHN, "):
        read_part(path, "XY.MYSTN.00.BHZ")


def test_read_part_refuses_what_obspy_cannot_read(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("not a response")

    with pytest.raises(ValueError, match="Unknown format"):
        read_part(path)
    with pytest.raises(FileNotFoundError):
        read_part(tmp_path / "missing.xml")


def test_placeholder_inventory_has_the_shape_of_the_service():
    service = obspy.read_inventory(DATA_DIR / "nrl_part_centaur.xml")
    response = service[0][0][0].response

    inventory = placeholder_inventory(response, 100.0)

    [network] = inventory
    [station] = network
    [channel] = station
    expected = service[0][0][0]
    assert (network.code, station.code) == (service[0].code, service[0][0].code)
    assert (channel.code, channel.location_code) == (
        expected.code,
        expected.location_code,
    )
    assert channel.start_date == expected.start_date
    assert channel.sample_rate == 100.0
    assert channel.response is response
