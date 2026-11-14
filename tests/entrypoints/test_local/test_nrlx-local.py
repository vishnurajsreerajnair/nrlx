from __future__ import annotations

import obspy
from typer.testing import CliRunner

from nrlx.io.local import get_tree_dir
from nrlx.tools.cmd import app

runner = CliRunner()


def test_local_sync_installs_the_copy(
    tmp_path, fake_service, catalog_content, prefixes_content, nrl_zip
):
    fake_service.contents["catalog"] = catalog_content
    fake_service.contents["prefix-lookup"] = prefixes_content
    fake_service.contents["combine"] = nrl_zip

    result = runner.invoke(
        app, ["local", "sync", "--cache-root", str(tmp_path)], terminal_width=200
    )

    assert result.exit_code == 0, result.output
    assert "Local NRL synced" in result.output
    assert "Response files: 2" in result.output
    assert "note: no file in the NRL zip: sensor_Streckeisen_STS-1_LP360" in (
        result.output
    )
    assert get_tree_dir(tmp_path).is_dir()


def test_local_sync_service_error(tmp_path, fake_service):
    fake_service.status_code = 503

    result = runner.invoke(app, ["local", "sync", "--cache-root", str(tmp_path)])

    assert result.exit_code == 1
    assert "NRL service request failed" in result.output
    assert not get_tree_dir(tmp_path).exists()


def test_local_status_without_and_with_a_copy(tmp_path, local_tree):
    without = runner.invoke(app, ["local", "status", "--cache-root", str(tmp_path)])
    tree = get_tree_dir(tmp_path)
    tree.parent.mkdir(parents=True)
    local_tree.rename(tree)
    present = runner.invoke(
        app, ["local", "status", "--cache-root", str(tmp_path)], terminal_width=200
    )

    assert without.exit_code == 0
    assert "No local NRL copy" in without.output
    assert present.exit_code == 0, present.output
    assert "Response files: 2" in present.output
    assert "Synced: " in present.output


def test_local_remove_asks_first(tmp_path, local_tree):
    tree = get_tree_dir(tmp_path)
    tree.parent.mkdir(parents=True)
    local_tree.rename(tree)
    arguments = ["local", "remove", "--cache-root", str(tmp_path)]

    kept = runner.invoke(app, arguments, input="n\n")
    removed = runner.invoke(app, arguments, input="y\n")

    assert kept.exit_code == 0
    assert "Remove the local NRL copy" in kept.output
    assert "Kept." in kept.output
    assert removed.exit_code == 0
    assert "Local NRL removed" in removed.output
    assert not tree.exists()


def test_local_remove_yes_and_nothing_to_remove(tmp_path, local_tree):
    tree = get_tree_dir(tmp_path)
    tree.parent.mkdir(parents=True)
    local_tree.rename(tree)
    arguments = ["local", "remove", "--yes", "--cache-root", str(tmp_path)]

    removed = runner.invoke(app, arguments)
    again = runner.invoke(app, arguments)

    assert removed.exit_code == 0
    assert "Remove the local NRL copy" not in removed.output
    assert not tree.exists()
    assert again.exit_code == 0
    assert "No local NRL copy" in again.output


def test_response_source_local_writes_without_requests(
    cache_root, local_tree, fake_service, tmp_path
):
    tree = get_tree_dir(cache_root)
    local_tree.rename(tree)
    output = tmp_path / "st.xml"
    arguments = [
        "response",
        "--sensor",
        "STS-2,SG=1500",
        "--datalogger",
        "Q330",
        "--source",
        "local",
        "--cache-root",
        str(cache_root),
    ]

    line = runner.invoke(app, arguments, terminal_width=300)
    written = runner.invoke(app, [*arguments, "-o", str(output)])

    assert line.exit_code == 0, line.output
    assert "--source local -o FILE" in line.output
    assert written.exit_code == 0, written.output
    assert fake_service.requests == []
    assert obspy.read_inventory(output)[0][0][0].sample_rate == 40.0


def test_response_source_local_without_a_copy(cache_root, tmp_path):
    result = runner.invoke(
        app,
        [
            "response",
            "--sensor",
            "STS-1",
            "--source",
            "local",
            "-o",
            str(tmp_path / "st.xml"),
            "--cache-root",
            str(cache_root),
        ],
    )

    assert result.exit_code == 1
    assert "run 'nrlx local sync'" in result.output
