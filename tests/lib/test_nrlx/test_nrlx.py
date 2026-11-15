from __future__ import annotations

from datetime import datetime
from pathlib import Path

import obspy
import pytest
from obspy import UTCDateTime

from nrlx.io.cache import get_catalog_file, get_prefixes_file
from nrlx.io.local import FULL_NRL_PARAMS, get_tree_dir
from nrlx.models.nrlx import Nrlx
from nrlx.version import __version__

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


# the local copy
def test_sync_local_installs_the_tree_and_notes_the_missing_files(
    tmp_path, fake_service, catalog_content, prefixes_content, nrl_zip
):
    fake_service.contents["catalog"] = catalog_content
    fake_service.contents["prefix-lookup"] = prefixes_content
    fake_service.contents["combine"] = nrl_zip

    nrl, notes = Nrlx.sync_local(tmp_path)

    tree = get_tree_dir(tmp_path)
    assert nrl.local_tree == tree
    assert (tree / "index.txt").is_file()
    assert get_catalog_file(tmp_path).read_bytes() == catalog_content
    assert fake_service.requests[2].params == FULL_NRL_PARAMS
    # the catalog has five configurations, the zip two
    assert len(notes) == 3
    assert "no file in the NRL zip: sensor_Streckeisen_STS-1_LP360" in notes
    assert sorted(path.name for path in tree.parent.iterdir()) == [
        "NRL",
        "catalog.json",
        "prefixes.json",
    ]
    assert Nrlx.from_cache(tmp_path).local_tree == tree


def test_sync_local_failure_keeps_the_previous_copy(
    cache_root, fake_service, catalog_content, prefixes_content
):
    tree = get_tree_dir(cache_root)
    (tree / "sensor").mkdir(parents=True)
    fake_service.contents["catalog"] = catalog_content.replace(b"STS-1", b"STS-9")
    fake_service.contents["prefix-lookup"] = prefixes_content
    fake_service.contents["combine"] = b"<html>maintenance</html>"

    with pytest.raises(ValueError, match="is not a zip"):
        Nrlx.sync_local(cache_root)

    # the copy, the catalog and nothing staged
    assert (tree / "sensor").is_dir()
    assert get_catalog_file(cache_root).read_bytes() == catalog_content
    assert sorted(path.name for path in tree.parent.iterdir()) == [
        "NRL",
        "catalog.json",
        "prefixes.json",
    ]


def test_response_from_the_local_copy_combines_without_requests(
    catalog, prefixes, local_tree, fake_service
):
    nrl = Nrlx(catalog=catalog, prefixes=prefixes, local_tree=local_tree)

    inventory, notes = nrl.response(
        sensor=["STS-2", "SG=1500"],
        datalogger=["Q330"],
        source="local",
        channels=["HHZ"],
    )

    assert fake_service.requests == []
    channel = inventory[0][0][0]
    assert channel.code == "HHZ"
    assert channel.sample_rate == pytest.approx(40.0)
    assert channel.response.instrument_sensitivity.input_units.upper() == "M/S"
    assert notes == []


def test_response_of_a_part_alone_from_the_local_copy_is_its_file(
    catalog, prefixes, local_tree, fake_service
):
    nrl = Nrlx(catalog=catalog, prefixes=prefixes, local_tree=local_tree)
    expected = obspy.read_inventory(DATA_DIR / "nrl_part_sts2.xml")[0][0][0]

    inventory, notes = nrl.response(sensor=["STS-2", "SG=1500"], source="local")

    assert fake_service.requests == []
    assert notes == []
    assert inventory[0][0][0].response == expected.response


def test_response_from_a_file_and_the_local_copy(
    catalog, prefixes, local_tree, fake_service
):
    nrl = Nrlx(catalog=catalog, prefixes=prefixes, local_tree=local_tree)
    sensor = obspy.read_inventory(DATA_DIR / "nrl_part_ea120.xml")[0][0][0].response

    _, notes = nrl.response(sensor_response=sensor, datalogger=["Q330"], source="local")

    assert fake_service.requests == []
    assert [note.split(":")[0] for note in notes] == ["stage 1"]


def test_response_from_a_missing_local_copy(nrl, catalog, prefixes, tmp_path):
    with pytest.raises(FileNotFoundError, match="run 'nrlx local sync'"):
        nrl.response(sensor=["STS-1"], source="local")

    # a copy synced before the catalog had the part
    (tmp_path / "NRL").mkdir()
    synced = Nrlx(catalog=catalog, prefixes=prefixes, local_tree=tmp_path / "NRL")
    with pytest.raises(FileNotFoundError, match="STS-1_LP360 is not in the local"):
        synced.response(sensor=["STS-1"], source="local")


def test_response_of_the_service_notes_what_it_keeps_as_received(nrl, fake_service):
    fake_service.contents["combine"] = (DATA_DIR / "nrl_ea120_centaur.xml").read_bytes()

    _, notes = nrl.response(sensor=["STS-2", "SG=1500"], datalogger=["Q330"])

    assert [note.split(":")[0] for note in notes] == ["stage 1"]
    assert "kept as received" in notes[0]


def test_response_of_a_local_part_alone_notes_what_it_keeps(
    catalog, prefixes, tmp_path, fake_service
):
    # the EA-120 + Centaur channel as the file of the STS-2
    tree = tmp_path / "NRL"
    part = tree / "sensor" / "Streckeisen" / "STS-2_EG3_SG1500_LP120_STgroundVel.xml"
    part.parent.mkdir(parents=True)
    part.write_bytes((DATA_DIR / "nrl_ea120_centaur.xml").read_bytes())
    nrl = Nrlx(catalog=catalog, prefixes=prefixes, local_tree=tree)

    _, notes = nrl.response(sensor=["STS-2", "SG=1500"], source="local")

    assert fake_service.requests == []
    assert "kept as received" in notes[0]


def test_response_says_what_built_each_channel(nrl, fake_service, make_stationxml):
    fake_service.contents["combine"] = make_stationxml("ZZZ")

    inventory, _ = nrl.response(
        sensor=["STS-2", "SG=1500"], datalogger=["Q330"], channels=["HHZ", "HHN"]
    )

    comments = [channel.comments for channel in inventory[0][0]]
    assert [[comment.subject for comment in each] for each in comments] == [
        ["nrlx"],
        ["nrlx"],
    ]
    assert comments[0][0].value == (
        f"built by nrlx {__version__}: sensor={SENSOR} datalogger={DATALOGGER}"
    )


def test_response_says_file_for_a_part_from_a_file(nrl, fake_service):
    fake_service.contents["combine"] = (DATA_DIR / "nrl_part_q330hr.xml").read_bytes()
    sensor = obspy.read_inventory(DATA_DIR / "nrl_part_ea120.xml")[0][0][0].response

    inventory, _ = nrl.response(sensor_response=sensor, datalogger=["Q330"])

    [comment] = inventory[0][0][0].comments
    assert comment.value.endswith(f": sensor=file datalogger={DATALOGGER}")


def test_assets_of_the_cache(cache_root, tmp_path):
    assert Nrlx.from_cache(cache_root).assets.db == cache_root / "assets.sqlite"
    custom = Nrlx.from_cache(cache_root, assets_db=tmp_path / "company.sqlite")
    assert custom.assets.db == tmp_path / "company.sqlite"
