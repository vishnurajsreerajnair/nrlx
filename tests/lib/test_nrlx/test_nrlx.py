from __future__ import annotations

from datetime import datetime
from pathlib import Path

import obspy
import pytest
from obspy import UTCDateTime

from nrlx.io.cache import get_catalog_file, get_prefixes_file
from nrlx.models.nrlx import Nrlx

DATA_DIR = Path(__file__).parents[2] / "data"


def test_from_cache(cache_root):
    nrl = Nrlx.from_cache(cache_root, base_url="https://isamgeo.in/nrl/")

    assert nrl.base_url == "https://isamgeo.in/nrl/"
    assert len(nrl.catalog.get_configurations()) == 5
    assert [prefix.prefix for prefix in nrl.prefixes] == ["FR", "FV", "LP", "SG"]


def test_from_cache_without_catalog_says_sync(tmp_path):
    with pytest.raises(FileNotFoundError, match="Run 'nrlx sync'"):
        Nrlx.from_cache(tmp_path)


def test_from_cache_without_code_table_says_sync(cache_root):
    get_prefixes_file(cache_root).unlink()

    with pytest.raises(FileNotFoundError, match="Code table not found"):
        Nrlx.from_cache(cache_root)


def test_sync_downloads_the_catalog_and_returns_a_ready_nrlx(
    tmp_path, fake_service, catalog_content, prefixes_content
):
    fake_service.contents["catalog"] = catalog_content
    fake_service.contents["prefix-lookup"] = prefixes_content

    nrl = Nrlx.sync(tmp_path)

    assert get_catalog_file(tmp_path).read_bytes() == catalog_content
    assert get_prefixes_file(tmp_path).read_bytes() == prefixes_content
    assert len(nrl.prefixes) == 4
    assert fake_service.requests[1].params == {"format": "json", "nodata": 404}
    assert nrl.catalog.resolve("sensor", ["STS-1"], nrl.prefixes).instconfig == (
        "sensor_Streckeisen_STS-1_LP360"
    )


def test_sync_keeps_the_previous_catalog_on_invalid_download(
    cache_root, fake_service, catalog_content
):
    fake_service.contents["catalog"] = b"<html>maintenance</html>"

    with pytest.raises(ValueError, match="Invalid catalog"):
        Nrlx.sync(cache_root)
    assert get_catalog_file(cache_root).read_bytes() == catalog_content


def test_sync_invalid_code_table_keeps_both_previous_files(
    cache_root, fake_service, catalog_content, prefixes_content
):
    fake_service.contents["catalog"] = catalog_content.replace(b"STS-1", b"STS-9")
    fake_service.contents["prefix-lookup"] = b"<html>maintenance</html>"

    with pytest.raises(ValueError, match="Invalid code table"):
        Nrlx.sync(cache_root)
    assert get_catalog_file(cache_root).read_bytes() == catalog_content
    assert get_prefixes_file(cache_root).read_bytes() == prefixes_content


SENSOR = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
DATALOGGER = "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def test_find_uses_the_code_table(nrl):
    found = nrl.find(["STS-2", "SG=1500"], "sensor")

    assert [configuration.instconfig for *_, configuration in found.rows] == [SENSOR]


def test_response_resolves_the_parts_and_asks_once(nrl, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("ZZZ")

    inventory, notes = nrl.response(
        sensor=["STS-2", "SG=1500"],
        datalogger=["Q330"],
        network="XY",
        station="TST",
        location="00",
        channels=["HHZ", "HHN", "HHE"],
    )

    [request] = fake_service.requests
    assert request.url.endswith("/combine")
    assert request.params == {
        "instconfig": f"{SENSOR}:{DATALOGGER}",
        "format": "stationxml",
        "nodata": 404,
    }
    [network] = inventory
    [station] = network
    assert (network.code, station.code) == ("XY", "TST")
    assert [channel.code for channel in station] == ["HHZ", "HHN", "HHE"]
    assert notes == []


def test_response_places_the_channels(nrl, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("ZZZ")

    inventory, _ = nrl.response(
        sensor=["STS-2", "SG=1500"],
        channels=["HHZ"],
        starttime=datetime(2026, 1, 1),
        latitude=45.6,
        longitude=8.9,
        elevation=210.0,
        depth=2.0,
    )

    channel = inventory[0][0][0]
    assert (channel.latitude, channel.longitude, channel.elevation, channel.depth) == (
        45.6,
        8.9,
        210.0,
        2.0,
    )
    assert channel.start_date == UTCDateTime(2026, 1, 1)


def test_response_of_an_ambiguous_part_fails_before_any_request(nrl, fake_service):
    with pytest.raises(LookupError, match="Ambiguous sensor selection"):
        nrl.response(sensor=["STS-2"])
    assert fake_service.requests == []


def test_response_refuses_an_invalid_request(nrl, fake_service):
    with pytest.raises(ValueError, match="go as a sensor"):
        nrl.response(sensor=["STS-1"], soh=["temperature"])
    assert fake_service.requests == []


def test_response_combines_a_file_part_with_the_nrl_part_alone(nrl, fake_service):
    fake_service.contents["combine"] = (DATA_DIR / "nrl_part_q330hr.xml").read_bytes()
    sensor = obspy.read_inventory(DATA_DIR / "nrl_part_ea120.xml")[0][0][0].response

    inventory, notes = nrl.response(
        sensor_response=sensor,
        datalogger=["Q330"],
        network="XY",
        station="TST",
        channels=["HHZ", "HHN"],
    )

    # the datalogger asked alone, the Eentec normalization corrected
    [request] = fake_service.requests
    assert request.params["instconfig"] == DATALOGGER
    assert [note.split(":")[0] for note in notes] == ["stage 1"]
    [network] = inventory
    [station] = network
    assert (network.code, station.code) == ("XY", "TST")
    assert [channel.code for channel in station] == ["HHZ", "HHN"]
    channel = station[0]
    assert channel.location_code == "00"
    assert channel.sample_rate == pytest.approx(40.0)
    assert channel.response.response_stages[0].input_units.upper() == "M/S**2"
    assert channel.response.instrument_sensitivity.output_units.upper() == "COUNT"


def test_response_of_two_file_parts_asks_nothing(nrl, fake_service):
    sensor = obspy.read_inventory(DATA_DIR / "nrl_part_sts2.xml")[0][0][0].response
    datalogger = obspy.read_inventory(DATA_DIR / "nrl_part_centaur.xml")
    datalogger = datalogger[0][0][0].response

    inventory, _ = nrl.response(sensor_response=sensor, datalogger_response=datalogger)

    assert fake_service.requests == []
    assert inventory[0][0][0].code == "ZZZ"
