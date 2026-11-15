from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nrlx.core.assets import (
    check_uid,
    column_holds,
    provenance_text,
    read_provenance,
    read_source,
    split_asset_keys,
)
from nrlx.io.assets import read_rows
from nrlx.io.inventory import (
    label_channels,
    read_channels,
    read_stationxml,
    set_provenance,
)
from nrlx.models.assets import Assets

DATA_DIR = Path(__file__).parents[2] / "data"

SENSOR = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
DATALOGGER = "datalogger_Quanterra_Q330_FV40Vpp_FR100"


@pytest.fixture
def assets(tmp_path, catalog, prefixes) -> Assets:
    """Assets of an empty database in tmp_path, with the test catalog"""
    return Assets(db=tmp_path / "assets.sqlite", catalog=catalog, prefixes=prefixes)


def tellus(station: str):
    """Inventory of a Tellus on a Centaur at 100 sps, one channel of a station"""
    built = read_stationxml((DATA_DIR / "nrl_tellus_centaur.xml").read_bytes())
    return label_channels(built, "XY", station, "00", ["HHZ"], None, None)


# core


def test_provenance_reads_back_its_parts():
    text = provenance_text(
        "0.3.0", "service", [("sensor", SENSOR), ("datalogger", "file")]
    )

    assert text == f"built by nrlx 0.3.0 (service): sensor={SENSOR} datalogger=file"
    assert read_provenance(text) == [("sensor", SENSOR), ("datalogger", "file")]
    assert read_provenance("Calibrated on 2024-05-01: gain=1498") == []


@pytest.mark.parametrize(
    ("text", "source"),
    [
        (f"built by nrlx 0.3.0 (service): sensor={SENSOR}", "service"),
        (f"built by nrlx 0.3.0 (local): sensor={SENSOR}", "local"),
        # written before the source was recorded
        (f"built by nrlx 0.3.0: sensor={SENSOR}", None),
        ("Calibrated on 2024-05-01 (local): gain=1498", None),
    ],
)
def test_read_source_gives_the_source_or_none(text, source):
    assert read_source(text) == source


@pytest.mark.parametrize("uid", ["T13", "EB696", "SN-1234_a.b"])
def test_check_uid_keeps_a_folder_name(uid):
    assert check_uid(uid) == uid


@pytest.mark.parametrize("uid", ["", ".hidden", "../T13", "a b", "x/y"])
def test_check_uid_refuses_what_cannot_name_a_folder(uid):
    with pytest.raises(ValueError, match="must be letters, digits"):
        check_uid(uid)


def test_split_asset_keys_puts_rate_and_units_on_the_columns():
    parts, columns = split_asset_keys(["STS-2", "FR=100", "rate=40..100", "Units=m/s"])

    assert parts == ["STS-2", "FR=100"]
    assert columns == [
        ("rate", ">=", "40"),
        ("rate", "<=", "100"),
        ("units", "=", "m/s"),
    ]


def test_column_holds_on_the_rate_and_the_units():
    assert column_holds(40.0, "m/s", ("rate", "=", "40"))
    assert not column_holds(None, "m/s", ("rate", "=", "40"))
    assert column_holds(40.0, "M/S", ("units", "=", "m/s"))


# add


def test_add_numbers_the_versions_of_a_uid_across_variants(assets, station_xml):
    first = assets.add(read_channels(station_xml))
    second = assets.add(tellus("T13"))

    assert (first.uid, first.version, second.version) == ("T13", 1, 2)
    assert first.channels == ["XY.T13.00.HHZ", "XY.T13.00.HHN", "XY.T13.00.HHE"]
    assert (first.sample_rate, first.input_units) == (40.0, "m/s")
    assert first.sensitivity == pytest.approx(2.64095e9)
    assert (first.sensor, first.datalogger) == (None, None)
    assert [row.version for row in assets.list("T13")] == [1, 2]


def test_add_reads_the_parts_from_the_provenance(assets, station_xml):
    inventory = set_provenance(
        read_channels(station_xml),
        provenance_text(
            "0.3.0", "service", [("sensor", SENSOR), ("datalogger", DATALOGGER)]
        ),
    )

    row = assets.add(inventory, "EB696")

    assert (row.uid, row.sensor, row.datalogger) == ("EB696", SENSOR, DATALOGGER)


def test_add_refuses_the_same_response_twice(assets, station_xml):
    assets.add(read_channels(station_xml))
    relabelled = read_channels(station_xml, "XY.T13.00.HHZ")

    with pytest.raises(ValueError, match="T13 already has this response as v1."):
        assets.add(relabelled)


def test_add_of_a_deprecated_response_says_undo(assets, station_xml):
    assets.add(read_channels(station_xml))
    assets.deprecate("T13", 1)

    with pytest.raises(ValueError, match="deprecated: put it back with --undo"):
        assets.add(read_channels(station_xml))


def test_add_needs_a_uid_for_the_placeholder_or_several_stations(assets):
    placeholder = read_stationxml((DATA_DIR / "nrl_sts2_q330.xml").read_bytes())
    two = tellus("T13")
    two[0].stations += tellus("T14")[0].stations

    with pytest.raises(ValueError, match="placeholder YY: give a UID"):
        assets.add(placeholder)
    with pytest.raises(ValueError, match="stations T13, T14: give a UID"):
        assets.add(two)
    assert assets.add(placeholder, "EB696").uid == "EB696"


def test_add_refuses_channels_of_different_responses(assets, station_xml):
    mixed = read_channels(station_xml)
    mixed[0][0].channels += tellus("T13")[0][0].channels

    with pytest.raises(ValueError, match="an asset holds one response"):
        assets.add(mixed)


def test_add_refuses_a_uid_that_cannot_name_a_folder(assets, station_xml):
    with pytest.raises(ValueError, match="must be letters"):
        assets.add(read_channels(station_xml), "../T13")


# select and get


def test_select_takes_the_latest_in_use_and_any_version_by_number(assets, station_xml):
    inventory = read_channels(station_xml)
    assets.add(inventory)
    changed = read_channels(station_xml)
    for channel in changed[0][0]:
        channel.response.response_stages[0].stage_gain = 1498.0
        channel.response.recalculate_overall_sensitivity()
    assets.add(changed)

    assert assets.select("T13").version == 2
    assets.deprecate("T13", 2)
    assert assets.select("T13").version == 1
    assert assets.select("T13", version=2).version == 2
    assets.deprecate("T13", 2, undo=True)
    assert assets.select("T13").version == 2


def test_select_asks_a_key_between_variants(assets, station_xml):
    assets.add(read_channels(station_xml))
    assets.add(tellus("T13"))

    with pytest.raises(ValueError, match="T13 has 2 variants for these keys"):
        assets.select("T13")
    assert assets.select("T13", ["rate=40"]).version == 1
    assert assets.select("T13", ["rate=100", "units=m/s"]).version == 2


def test_select_by_the_keys_of_the_nrl_parts(assets, station_xml):
    marked = set_provenance(
        read_channels(station_xml),
        provenance_text(
            "0.3.0", "service", [("sensor", SENSOR), ("datalogger", DATALOGGER)]
        ),
    )
    assets.add(marked)
    assets.add(tellus("T13"))

    assert assets.select("T13", ["STS-2", "Q330"]).version == 1
    with pytest.raises(LookupError, match="No version of T13 in use matches sens=750"):
        assets.select("T13", ["sens=750"])


def test_select_keys_on_the_parts_need_the_catalog(tmp_path, station_xml):
    assets = Assets(db=tmp_path / "assets.sqlite")
    assets.add(read_channels(station_xml))

    with pytest.raises(ValueError, match="need the catalog: run nrlx sync"):
        assets.select("T13", ["STS-2"])


def test_select_unknown_uid_and_version_list_what_exists(assets, station_xml):
    assets.add(read_channels(station_xml))

    with pytest.raises(LookupError, match=r"No asset T14 .*\(assets: T13\)"):
        assets.select("T14")
    with pytest.raises(LookupError, match=r"T13 has no version 3 \(versions: 1\)"):
        assets.select("T13", version=3)


def test_get_gives_back_the_inventory_as_added(assets, station_xml):
    assets.add(read_channels(station_xml))

    inventory = assets.get("T13")

    [network] = inventory
    [station] = network
    assert [channel.code for channel in station] == ["HHZ", "HHN", "HHE"]


# delete


def test_delete_one_version_or_every_version(assets, station_xml):
    assets.add(read_channels(station_xml))
    assets.add(tellus("T13"))

    assert assets.delete("T13", 1) == 1
    assert [row.version for row in assets.list()] == [2]
    assert assets.delete("T13") == 1
    with pytest.raises(LookupError, match="No T13 in"):
        assets.delete("T13")


# the database


def test_reading_a_missing_database_does_not_create_it(tmp_path):
    path = tmp_path / "none.sqlite"

    assert read_rows(path) == []
    assert not path.exists()


def test_a_database_of_a_newer_layout_is_refused(assets, station_xml):
    assets.add(read_channels(station_xml))
    with sqlite3.connect(assets.db) as connection:
        connection.execute("PRAGMA user_version = 99")

    with pytest.raises(ValueError, match="layout 99 of a newer nrlx"):
        assets.list()


# export and import


def test_export_writes_a_file_per_version_and_the_manifest(
    assets, station_xml, tmp_path
):
    assets.add(read_channels(station_xml))
    assets.add(tellus("T13"))

    files = assets.export_to(tmp_path / "share")

    names = [str(path.relative_to(tmp_path / "share")) for path in files]
    assert names == ["T13/v1.xml", "T13/v2.xml", "manifest.json"]
    manifest = json.loads((tmp_path / "share" / "manifest.json").read_text())
    assert manifest["manifest_version"] == 1
    assert [row["version"] for row in manifest["assets"]] == [1, 2]
    assert "stationxml" not in manifest["assets"][0]


def test_export_refuses_a_folder_not_empty(assets, station_xml, tmp_path):
    assets.add(read_channels(station_xml))
    (tmp_path / "share").mkdir()
    (tmp_path / "share" / "notes.txt").write_text("mine")

    with pytest.raises(ValueError, match="is not empty"):
        assets.export_to(tmp_path / "share")


def test_import_of_an_export_or_a_database_skips_what_is_here(
    assets, station_xml, tmp_path
):
    assets.add(read_channels(station_xml))
    assets.add(tellus("T13"))
    assets.export_to(tmp_path / "share")
    other = Assets(db=tmp_path / "other.sqlite")

    assert other.import_from(tmp_path / "share") == (2, 0)
    assert other.import_from(assets.db) == (0, 2)
    assert [row.sha256 for row in other.list()] == [row.sha256 for row in assets.list()]


def test_import_refuses_a_version_that_differs_and_imports_nothing(
    assets, station_xml, tmp_path
):
    assets.add(read_channels(station_xml))
    assets.add(tellus("T13"))
    other = Assets(db=tmp_path / "other.sqlite")
    other.add(tellus("T13"))

    with pytest.raises(ValueError, match="T13 v1 differ from the versions here"):
        other.import_from(assets.db)
    assert [row.version for row in other.list()] == [1]


def test_import_refuses_a_file_changed_after_the_export(assets, station_xml, tmp_path):
    assets.add(read_channels(station_xml))
    assets.export_to(tmp_path / "share")
    path = tmp_path / "share" / "T13" / "v1.xml"
    path.write_text(path.read_text().replace("T13", "T99"))

    with pytest.raises(ValueError, match=r"T13/v1.xml changed since the export"):
        Assets(db=tmp_path / "other.sqlite").import_from(tmp_path / "share")


def test_import_of_a_missing_source(assets, tmp_path):
    with pytest.raises(FileNotFoundError, match="No export or database"):
        assets.import_from(tmp_path / "none")
