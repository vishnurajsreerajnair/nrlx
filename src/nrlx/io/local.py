"""The local copy of the NRL: the tree of the zip of the service, in the cache

The tree keeps the layout of the zip (NRL/<element>/<manufacturer>/<rest>.xml, with
the index and detail files), so obspy's NRL client can open it too.


"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from nrlx.io.cache import get_cache_root

# the request of the whole NRL, StationXML, to the /combine endpoint
FULL_NRL_PARAMS: dict[str, str | int] = {
    "instconfig": "full_NRL_v2_zip",
    "format": "stationxml.zip",
    "nodata": 404,
}

# the service builds the zip before answering
DOWNLOAD_TIMEOUT = 300.0

# the top folder of the zip
TREE_NAME = "NRL"


def get_tree_dir(cache_root: Path | None = None) -> Path:
    """Folder of the local copy in the cache, ROOT/nrl/NRL

    Args:
        cache_root: custom root folder, None for the platform cache folder of the
            user.

    Returns:
        path of the folder, which may not exist yet.


    """
    tree = get_cache_root(cache_root) / "nrl" / TREE_NAME

    return tree


def get_part_file(tree: Path, instconfig: str) -> Path:
    """File of a configuration in the local copy

    The instconfig is element_manufacturer_rest: the file is
    tree/element/manufacturer/rest.xml.

    Args:
        tree: folder of the local copy, see get_tree_dir.
        instconfig: exact instconfig of the configuration.

    Returns:
        path of the file, which may not exist.

    Raises:
        ValueError: if the instconfig has no element and manufacturer.


    """
    match instconfig.split("_", 2):
        case [element, manufacturer, rest] if element and manufacturer and rest:
            part_file = tree / element / manufacturer / f"{rest}.xml"
        case _:
            raise ValueError(
                f"{instconfig} is not an instconfig (element_manufacturer_...)."
            )

    return part_file


def extract_tree(zip_file: Path, target: Path) -> Path:
    """Unzip the NRL folder of the zip of the service into target

    Args:
        zip_file: zip of the whole NRL.
        target: folder to create, the content of NRL/ in it.

    Returns:
        the folder.

    Raises:
        ValueError: if the file is not a zip with an NRL folder, or a member would
            be written outside target.
        OSError: if the files cannot be written.


    """
    prefix = f"{TREE_NAME}/"
    root = target.resolve()
    try:
        with zipfile.ZipFile(zip_file) as archive:
            members = [
                info for info in archive.infolist() if info.filename.startswith(prefix)
            ]
            if not members:
                raise ValueError(f"{zip_file} is not an NRL zip: no {prefix} folder.")
            for info in members:
                # a member is written only inside target
                destination = (root / info.filename[len(prefix) :]).resolve()
                if not destination.is_relative_to(root):
                    raise ValueError(
                        f"{zip_file}: {info.filename} leaves the NRL folder."
                    )
                if info.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("wb") as file:
                        shutil.copyfileobj(source, file)
    except zipfile.BadZipFile as err:
        raise ValueError(f"{zip_file} is not a zip: {err}") from err

    return target


def missing_parts(tree: Path, instconfigs: list[str]) -> list[str]:
    """Configurations without their file in a tree

    Args:
        tree: folder of a local copy.
        instconfigs: exact instconfigs.

    Returns:
        the instconfigs whose file is missing, in their order.

    Raises:
        ValueError: see get_part_file.


    """
    missing = [
        instconfig
        for instconfig in instconfigs
        if not get_part_file(tree, instconfig).is_file()
    ]

    return missing


def install_tree(staged: Path, tree: Path) -> None:
    """Put a staged tree in place of the local copy

    The previous copy is renamed aside, then deleted once the new one is in place;
    if the rename fails it is put back. The two folders are on the same disk, so
    the renames are immediate.

    Args:
        staged: the new tree, next to tree.
        tree: folder of the local copy, see get_tree_dir.

    Raises:
        OSError: if a folder cannot be renamed or deleted.


    """
    previous = tree.with_name(f"{tree.name}.old")
    if previous.exists():
        shutil.rmtree(previous)
    if tree.exists():
        tree.rename(previous)
    try:
        staged.rename(tree)
    except OSError:
        if previous.exists():
            previous.rename(tree)
        raise
    if previous.exists():
        shutil.rmtree(previous)


def remove_tree(tree: Path) -> None:
    """Delete the local copy

    Args:
        tree: folder of the local copy, see get_tree_dir.

    Raises:
        FileNotFoundError: if there is no local copy.
        OSError: if it cannot be deleted.


    """
    if not tree.is_dir():
        raise FileNotFoundError(f"No local NRL copy in {tree}.")
    shutil.rmtree(tree)


def tree_size(tree: Path) -> tuple[int, int]:
    """Number of response files and size of a tree

    Args:
        tree: folder of a local copy.

    Returns:
        the number of XML files and the size of every file in bytes.


    """
    files = [path for path in tree.rglob("*") if path.is_file()]
    responses = sum(1 for path in files if path.suffix == ".xml")
    size = sum(path.stat().st_size for path in files)

    return responses, size
