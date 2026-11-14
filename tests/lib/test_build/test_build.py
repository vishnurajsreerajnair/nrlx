from __future__ import annotations

import pytest

from nrlx.io.inventory import read_stationxml
from nrlx.models.build import Build
from nrlx.models.instrument import Instrument


def test_a_request_without_channels(nrl, fake_service):
    fake_service.contents["combine"] = b"<xml/>"
    request = Build(sensor=Instrument(keys=["STS-1"]), network="XY")

    [(channel, response)] = request.build(nrl)

    assert channel is None
    assert response.content == b"<xml/>"
    [fakerequest] = fake_service.requests
    assert fakerequest.params == {
        "instconfig": "sensor_Streckeisen_STS-1_LP360",
        "format": "stationxml",
        "nodata": 404,
        "network": "XY",
    }


def test_a_request_for_each_channel(nrl, fake_service):
    request = Build(
        sensor=Instrument(keys=["STS-1"]),
        datalogger=Instrument(keys=["Q330"]),
        channels=["EHZ", "EHN"],
    )

    responses = request.build(nrl)

    assert [channel for channel, _ in responses] == ["EHZ", "EHN"]
    channels = [fakerequest.params["channel"] for fakerequest in fake_service.requests]
    assert channels == ["EHZ", "EHN"]
    assert {response.instconfig for _, response in responses} == {
        "sensor_Streckeisen_STS-1_LP360:datalogger_Quanterra_Q330_FV40Vpp_FR100"
    }


def test_ambiguous_selection_fails_before_any_request(nrl, fake_service):
    request = Build(sensor=Instrument(keys=["STS-2"]), channels=["EHZ", "EHN"])

    with pytest.raises(LookupError, match="Ambiguous sensor selection"):
        request.build(nrl)
    assert fake_service.requests == []


def test_merged_channels_in_a_single_stationxml(nrl, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("EHZ")
    request = Build(
        sensor=Instrument(keys=["STS-1"]),
        datalogger=Instrument(keys=["Q330"]),
        channels=["EHZ", "EHN", "EHE"],
        merge_channels=True,
    )

    [(channel, response)] = request.build(nrl)

    assert channel is None
    assert response.instconfig == (
        "sensor_Streckeisen_STS-1_LP360:datalogger_Quanterra_Q330_FV40Vpp_FR100"
    )
    assert len(fake_service.requests) == 3
    station = read_stationxml(response.content)[0][0]
    assert len(station.channels) == 3


def test_coordinates_on_the_merged_stationxml(nrl, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("EHZ")
    request = Build(
        sensor=Instrument(keys=["STS-1"]),
        channels=["EHZ", "EHN"],
        merge_channels=True,
        latitude=49.096,
        longitude=8.432,
        elevation=112.0,
    )

    [(_, response)] = request.build(nrl)

    station = read_stationxml(response.content)[0][0]
    assert (station.latitude, station.longitude, station.elevation) == (
        49.096,
        8.432,
        112.0,
    )
    assert [channel.depth for channel in station] == [0.0, 0.0]


def test_coordinates_on_each_channel_file(nrl, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("EHZ")
    request = Build(
        sensor=Instrument(keys=["STS-1"]),
        channels=["EHZ", "EHN"],
        latitude=49.096,
        longitude=8.432,
        depth=25.0,
    )

    responses = request.build(nrl)

    assert [channel for channel, _ in responses] == ["EHZ", "EHN"]
    assert [
        read_stationxml(response.content)[0][0][0].depth for _, response in responses
    ] == [25.0, 25.0]
