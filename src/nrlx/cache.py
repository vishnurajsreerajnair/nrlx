"""Local cache layout and catalog download.

Resolves the platform-specific cache directory and syncs the NRL catalog into
it. ``CacheInfo`` is a plain data record; the module functions are the cache API.


"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_cache_dir

from nrlx.client import NRLClient
from nrlx.exceptions import NrlxCacheError

APP_NAME = "nrlx"
APP_AUTHOR = "nrlx"
NRL_SUBDIR = "nrl"
CATALOG_FILE_NAME = "catalog.json"


@dataclass(frozen=True)
class CacheInfo:
    """Information about the local nrlx cache.

    Args:
        root: Root cache directory used by nrlx.
        nrl_dir: Directory reserved for NRL data.
        exists: Whether the cache root already exists.


    """
    root: Path
    nrl_dir: Path
    exists: bool


def get_default_cache_root() -> Path:
    """Return the default user-specific cache directory for nrlx.

    Returns:
        Path to the default cache directory.


    """
    return Path(
        user_cache_dir(
            appname=APP_NAME,
            appauthor=APP_AUTHOR
        )
    )


def get_cache_info(cache_root: Path | None = None) -> CacheInfo:
    """Return local cache path information.

    Args:
        cache_root: Custom cache root; defaults to the platform user cache dir.

    Returns:
        CacheInfo describing the resolved cache paths.


    """
    root = cache_root.expanduser().resolve() if cache_root else get_default_cache_root()
    nrl_dir = root / NRL_SUBDIR

    return CacheInfo(
        root=root,
        nrl_dir=nrl_dir,
        exists=root.exists()
    )


def get_catalog_file(cache_root: Path | None = None) -> Path:
    """Return the path to the locally cached catalog file.

    Args:
        cache_root: Custom cache root; defaults to the platform user cache dir.

    Returns:
        Path to the local catalog file. Callers that need the file to exist
        should use Catalog.from_file, which raises NrlxCacheError with a
        clear message when it's missing.


    """
    return get_cache_info(cache_root).nrl_dir / CATALOG_FILE_NAME


def init_cache(cache_root: Path | None = None) -> CacheInfo:
    """Create the local nrlx cache directory.

    Args:
        cache_root: Custom cache root; defaults to the platform user cache dir.

    Returns:
        CacheInfo describing the initialized cache.

    Raises:
        NrlxCacheError: If the cache directory cannot be created.


    """
    info = get_cache_info(cache_root)

    try:
        info.nrl_dir.mkdir(
            parents=True,
            exist_ok=True
        )
    except OSError as exc:
        raise NrlxCacheError(f"Failed to initialize cache at {info.root}") from exc

    return get_cache_info(info.root)


def sync_catalog(
    cache_root: Path | None = None,
    *,
    base_url: str | None = None,
) -> Path:
    """Sync the local cache with the current remote NRL catalog.

    Creates the cache directory if it doesn't exist yet, then downloads the
    current catalog - safe to run on a fresh machine or to refresh later.

    Args:
        cache_root: Optional custom cache root.
        base_url: Optional custom NRL service base URL.

    Returns:
        Path to the downloaded catalog file.

    Raises:
        NrlxCacheError: If the cache cannot be initialized.
        NrlxNetworkError: If the catalog download fails.


    """
    cache = init_cache(cache_root)
    client = NRLClient.for_base_url(base_url)

    return client.download(
        "catalog",
        cache.nrl_dir / CATALOG_FILE_NAME
    )
