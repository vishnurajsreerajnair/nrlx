from __future__ import annotations

import io
import zipfile

import pytest

from nrlx.io.local import (
    extract_tree,
    get_part_file,
    get_tree_dir,
    install_tree,
    missing_parts,
    remove_tree,
    tree_size,
)

SENSOR = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
DATALOGGER = "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def test_tree_is_in_the_nrl_folder_of_the_cache(tmp_path):
    assert get_tree_dir(tmp_path) == tmp_path.resolve() / "nrl" / "NRL"


def test_part_file_splits_the_element_and_the_manufacturer(tmp_path):
    assert get_part_file(tmp_path, SENSOR) == (
        tmp_path / "sensor" / "Streckeisen" / "STS-2_EG3_SG1500_LP120_STgroundVel.xml"
    )
    with pytest.raises(ValueError, match="not an instconfig"):
        get_part_file(tmp_path, "sensor_Streckeisen")


def test_extract_tree_writes_the_content_of_the_nrl_folder(tmp_path, nrl_zip):
    zip_file = tmp_path / "NRL.zip"
    zip_file.write_bytes(nrl_zip)

    tree = extract_tree(zip_file, tmp_path / "staged")

    assert (tree / "index.txt").read_bytes() == b"index"
    assert get_part_file(tree, SENSOR).is_file()
    assert missing_parts(tree, [SENSOR, DATALOGGER, "sensor_Streckeisen_STS-1"]) == [
        "sensor_Streckeisen_STS-1"
    ]


def make_zip(names: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name in names:
            archive.writestr(name, b"x")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"not a zip", "is not a zip"),
        (make_zip(["other/file.xml"]), "no NRL/ folder"),
        (make_zip(["NRL/../../evil.xml"]), "leaves the NRL folder"),
    ],
)
def test_extract_tree_refuses_what_is_not_an_nrl_zip(tmp_path, content, message):
    zip_file = tmp_path / "NRL.zip"
    zip_file.write_bytes(content)

    with pytest.raises(ValueError, match=message):
        extract_tree(zip_file, tmp_path / "staged")
    assert not (tmp_path.parent / "evil.xml").exists()


def test_install_tree_replaces_the_previous_copy(tmp_path):
    tree = tmp_path / "NRL"
    (tree / "old").mkdir(parents=True)
    staged = tmp_path / "NRL.new"
    (staged / "new").mkdir(parents=True)

    install_tree(staged, tree)

    assert (tree / "new").is_dir()
    assert not (tree / "old").exists()
    assert not staged.exists()
    assert not (tmp_path / "NRL.old").exists()


def test_install_tree_without_a_previous_copy(tmp_path):
    staged = tmp_path / "NRL.new"
    staged.mkdir()

    install_tree(staged, tmp_path / "NRL")

    assert (tmp_path / "NRL").is_dir()


def test_tree_size_and_remove(local_tree):
    responses, size = tree_size(local_tree)

    assert responses == 2
    assert size > 0
    remove_tree(local_tree)
    assert not local_tree.exists()
    with pytest.raises(FileNotFoundError, match="No local NRL copy"):
        remove_tree(local_tree)
