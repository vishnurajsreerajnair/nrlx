"""Local cache of nrlx: its folders, the catalog file and the code table"""

from __future__ import annotations

from pathlib import Path

import msgspec
from platformdirs import user_cache_dir

from nrlx.models.catalog import Catalog
from nrlx.schema.cache import CatalogFileInput
from nrlx.schema.prefixes import PrefixInput


def get_cache_root(cache_root: Path | None = None) -> Path:
    """Root folder of the cache: the given one, or the cache folder of the user

    Args:
        cache_root: custom root folder, None for the platform cache folder of the
            user (for example ~/.cache/nrlx on Linux).

    Returns:
        absolute path of the root folder.


    """
    root = Path(user_cache_dir(appname="nrlx", appauthor="nrlx"))
    if cache_root is not None:
        root = cache_root.expanduser().resolve()

    return root


def get_catalog_file(cache_root: Path | None = None) -> Path:
    """Path of the catalog file in the cache, ROOT/nrl/catalog.json

    Args:
        cache_root: custom root folder, None for the platform cache folder of the
            user.

    Returns:
        path of the catalog file, which may not exist yet.


    """
    catalog_file = get_cache_root(cache_root) / "nrl" / "catalog.json"

    return catalog_file


def decode_catalog(content: bytes) -> Catalog:
    """Decode and validate the JSON catalog of the NRL service

    Args:
        content: JSON of the /catalog endpoint.

    Returns:
        the catalog.

    Raises:
        msgspec.DecodeError: if the content is not JSON or not the catalog
            structure. It is a ValueError.


    """
    catalog = msgspec.json.decode(content, type=CatalogFileInput).catalog

    return catalog


def read_catalog(catalog_file: Path) -> Catalog:
    """Read the catalog file of the cache

    Args:
        catalog_file: path of the catalog file, see get_catalog_file.

    Returns:
        the catalog.

    Raises:
        FileNotFoundError: if the catalog has not been synced yet.
        ValueError: if the file is not a valid catalog.
        OSError: if the file cannot be read.


    """
    # a missing catalog has not been synced yet
    if not catalog_file.exists():
        raise FileNotFoundError(
            f"Catalog file not found: {catalog_file}. Run 'nrlx sync'."
        )

    try:
        catalog = decode_catalog(catalog_file.read_bytes())
    except msgspec.DecodeError as err:
        raise ValueError(
            f"Invalid catalog file {catalog_file}. {err}. Run 'nrlx sync'."
        ) from err

    return catalog


def write_catalog(content: bytes, catalog_file: Path) -> Path:
    """Write the catalog file of the cache, creating its folders

    Args:
        content: JSON of the /catalog endpoint, validated with decode_catalog.
        catalog_file: path of the catalog file, see get_catalog_file.

    Returns:
        path of the catalog file.

    Raises:
        OSError: if the folders or the file cannot be written.


    """
    catalog_file.parent.mkdir(parents=True, exist_ok=True)
    catalog_file.write_bytes(content)

    return catalog_file


def get_prefixes_file(cache_root: Path | None = None) -> Path:
    """Path of the code table in the cache, ROOT/nrl/prefixes.json

    Args:
        cache_root: custom root folder, None for the platform cache folder of the
            user.

    Returns:
        path of the code table, which may not exist yet.


    """
    prefixes_file = get_cache_root(cache_root) / "nrl" / "prefixes.json"

    return prefixes_file


def decode_prefixes(content: bytes) -> list[PrefixInput]:
    """Decode and validate the code table of the NRL service

    Args:
        content: JSON of the /prefix-lookup endpoint.

    Returns:
        the codes of the instconfig parameters.

    Raises:
        msgspec.DecodeError: if the content is not JSON or not the table
            structure. It is a ValueError.


    """
    prefixes = msgspec.json.decode(content, type=list[PrefixInput])

    return prefixes


def read_prefixes(prefixes_file: Path) -> list[PrefixInput]:
    """Read the code table of the cache

    Args:
        prefixes_file: path of the code table, see get_prefixes_file.

    Returns:
        the codes of the instconfig parameters.

    Raises:
        FileNotFoundError: if the table has not been synced yet, as in the caches
            synced before nrlx 0.3.
        ValueError: if the file is not a valid table.
        OSError: if the file cannot be read.


    """
    # a missing table has not been synced yet
    if not prefixes_file.exists():
        raise FileNotFoundError(
            f"Code table not found: {prefixes_file}. Run 'nrlx sync'."
        )

    try:
        prefixes = decode_prefixes(prefixes_file.read_bytes())
    except msgspec.DecodeError as err:
        raise ValueError(
            f"Invalid code table {prefixes_file}. {err}. Run 'nrlx sync'."
        ) from err

    return prefixes


def write_prefixes(content: bytes, prefixes_file: Path) -> Path:
    """Write the code table of the cache, creating its folders

    Args:
        content: JSON of the /prefix-lookup endpoint, validated with
            decode_prefixes.
        prefixes_file: path of the code table, see get_prefixes_file.

    Returns:
        path of the code table.

    Raises:
        OSError: if the folders or the file cannot be written.


    """
    prefixes_file.parent.mkdir(parents=True, exist_ok=True)
    prefixes_file.write_bytes(content)

    return prefixes_file
