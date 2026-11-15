from __future__ import annotations

from pathlib import Path

import obspy
from typer.testing import CliRunner

from nrlx.models.assets import Assets
from nrlx.tools.cmd import app

runner = CliRunner()

DATA_DIR = Path(__file__).parents[2] / "data"


def test_assets_add_list_and_get(station_xml, tmp_path):
    db = tmp_path / "assets.sqlite"
    output = tmp_path / "t13.resp"

    added = runner.invoke(app, ["assets", "add", str(station_xml), "--db", str(db)])
    listed = runner.invoke(
        app, ["assets", "list", "--db", str(db)], env={"COLUMNS": "200"}
    )
    got = runner.invoke(
        app, ["assets", "get", "T13", "rate=40", "-o", str(output), "--db", str(db)]
    )

    assert added.exit_code == 0, added.output
    assert "Added T13 v1" in added.output
    assert listed.exit_code == 0, listed.output
    assert "T13" in listed.output
    assert "in use" in listed.output
    assert got.exit_code == 0, got.output
    assert "T13 v1 written (resp)" in got.output
    [network] = obspy.read_inventory(str(output))
    assert [cha.code for sta in network for cha in sta] == ["HHZ", "HHN", "HHE"]


def test_assets_add_twice_fails(station_xml, tmp_path):
    db = tmp_path / "assets.sqlite"
    runner.invoke(app, ["assets", "add", str(station_xml), "--db", str(db)])

    result = runner.invoke(app, ["assets", "add", str(station_xml), "--db", str(db)])

    assert result.exit_code == 1
    assert "T13 already has this response as v1" in result.output


def test_assets_list_of_an_empty_database(tmp_path):
    db = tmp_path / "assets.sqlite"

    result = runner.invoke(app, ["assets", "list", "--db", str(db)])

    assert result.exit_code == 0
    assert "No assets in" in result.output
    assert not db.exists()


def test_assets_get_unknown_uid(tmp_path):
    result = runner.invoke(
        app,
        [
            "assets",
            "get",
            "T13",
            "-o",
            str(tmp_path / "a.xml"),
            "--db",
            str(tmp_path / "a.sqlite"),
        ],
        terminal_width=200,
    )

    assert result.exit_code == 1
    assert "Error: No asset T13" in result.output


def test_assets_deprecate_then_undo(station_xml, tmp_path):
    db = tmp_path / "assets.sqlite"
    runner.invoke(app, ["assets", "add", str(station_xml), "--db", str(db)])
    output = str(tmp_path / "a.xml")

    deprecated = runner.invoke(
        app, ["assets", "deprecate", "T13", "--version", "1", "--db", str(db)]
    )
    refused = runner.invoke(
        app, ["assets", "get", "T13", "-o", output, "--db", str(db)]
    )
    undone = runner.invoke(
        app, ["assets", "deprecate", "T13", "--version", "1", "--undo", "--db", str(db)]
    )
    got = runner.invoke(app, ["assets", "get", "T13", "-o", output, "--db", str(db)])

    assert "T13 v1 deprecated." in deprecated.output
    assert refused.exit_code == 1
    assert "No version of T13 in use" in refused.output
    assert "T13 v1 back in use." in undone.output
    assert got.exit_code == 0, got.output


def test_assets_delete_asks_first(station_xml, tmp_path):
    db = tmp_path / "assets.sqlite"
    runner.invoke(app, ["assets", "add", str(station_xml), "--db", str(db)])

    kept = runner.invoke(app, ["assets", "delete", "T13", "--db", str(db)], input="n\n")
    deleted = runner.invoke(app, ["assets", "delete", "T13", "--yes", "--db", str(db)])

    assert "Nothing deleted." in kept.output
    assert "Deleted 1 version of T13." in deleted.output
    assert Assets(db=db).list() == []


def test_assets_export_then_import(station_xml, tmp_path):
    db = tmp_path / "assets.sqlite"
    other = tmp_path / "other.sqlite"
    share = tmp_path / "share"
    runner.invoke(app, ["assets", "add", str(station_xml), "--db", str(db)])

    exported = runner.invoke(app, ["assets", "export", str(share), "--db", str(db)])
    imported = runner.invoke(app, ["assets", "import", str(share), "--db", str(other)])
    again = runner.invoke(app, ["assets", "import", str(db), "--db", str(other)])

    assert "Exported 1 versions" in exported.output
    assert (share / "T13" / "v1.xml").is_file()
    assert "Imported 1 versions, 0 already here" in imported.output
    assert "Imported 0 versions, 1 already here" in again.output


def test_response_add_asset_without_writing_a_file(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    db = tmp_path / "assets.sqlite"
    command = [
        "response",
        "--sensor",
        "STS-1",
        "--station",
        "TST",
        "--add-asset",
        "--db",
        str(db),
        "--cache-root",
        str(cache_root),
    ]

    first = runner.invoke(app, command, terminal_width=200)
    second = runner.invoke(app, command, terminal_width=200)

    assert first.exit_code == 0, first.output
    assert "Added asset TST v1" in first.output
    assert second.exit_code == 0, second.output
    assert "TST already has this response as v1: not added" in second.output
    [row] = Assets(db=db).list()
    assert row.sensor == "sensor_Streckeisen_STS-1_LP360"


def test_response_add_asset_with_a_uid_and_a_file(
    cache_root, fake_service, make_stationxml, tmp_path
):
    fake_service.contents["combine"] = make_stationxml("ZZZ")
    db = tmp_path / "assets.sqlite"
    output = tmp_path / "st.xml"

    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "--add-asset",
            "--uid",
            "EB696",
            "-o",
            str(output),
            "--db",
            str(db),
            "--cache-root",
            str(cache_root),
        ],
        terminal_width=200,
    )

    assert result.exit_code == 0, result.output
    assert "Response written (stationxml)" in result.output
    assert "Added asset EB696 v1" in result.output
    assert "built by nrlx" in output.read_text()


def test_response_add_asset_needs_a_uid_before_any_request(
    cache_root, fake_service, tmp_path
):
    base = ["response", "--sensor", "STS-1", "--cache-root", str(cache_root)]

    missing = runner.invoke(app, [*base, "--add-asset"])
    alone = runner.invoke(app, [*base, "--uid", "EB696"])
    invalid = runner.invoke(app, [*base, "--add-asset", "--uid", "../x"])

    assert missing.exit_code == 1
    assert "--add-asset needs --station or --uid" in missing.output
    assert alone.exit_code == 1
    assert "--uid names the asset of --add-asset" in alone.output
    assert invalid.exit_code == 1
    assert "must be letters" in invalid.output
    assert fake_service.requests == []
