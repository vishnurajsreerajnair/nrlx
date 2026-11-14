"""Local cache of nrlx: its folders and the catalog file"""

from __future__ import annotations

from pathlib import Path

import msgspec
from platformdirs import user_cache_dir

from nrlx.models.catalog import Catalog
from nrlx.schema.cache import CatalogFileInput


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
