from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir

from nrlx.exceptions import NRLXCacheError
from nrlx.models import CacheInfo

APP_NAME = "nrlx"
APP_AUTHOR = "nrlx"
CACHE_INDEX_NAME = "index.json"
NRL_SUBDIR = "nrl"


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
        cache_root: Optional custom cache root. If omitted, the platform-specific
            user cache directory is used.

    Returns:
        CacheInfo describing the resolved cache paths.
    
    
    """
    root = cache_root.expanduser().resolve() if cache_root else get_default_cache_root()
    nrl_dir = root / NRL_SUBDIR
    index_file = root / CACHE_INDEX_NAME

    return CacheInfo(
        root=root,
        nrl_dir=nrl_dir,
        index_file=index_file,
        exists=root.exists(),
    )

def init_cache(
    cache_root: Path | None = None, 
    *, 
    force: bool = False
) -> CacheInfo:
    """Create the local nrlx cache directory and index file.

    Args:
        cache_root: Optional custom cache root. If omitted, the platform-specific
            user cache directory is used.
        force: If True, rewrite the cache index even when it already exists.

    Returns:
        CacheInfo describing the initialized cache.

    Raises:
        NRLXCacheError: If the cache directory or index file cannot be created.
    
    
    """
    info = get_cache_info(cache_root)

    try:
        info.nrl_dir.mkdir(
            parents=True, 
            exist_ok=True
        )

        if force or not info.index_file.exists():
            index = _build_empty_index()
            info.index_file.write_text(
                json.dumps(index, indent=2),
                encoding="utf-8"
            )
    except OSError as exc:
        raise NRLXCacheError(f"Failed to initialize cache at {info.root}") from exc

    return get_cache_info(info.root)


def read_cache_index(cache_root: Path | None = None) -> dict[str, Any]:
    """Read the local nrlx cache index.

    Args:
        cache_root: Optional custom cache root. If omitted, the platform-specific
            user cache directory is used.

    Returns:
        Parsed cache index dictionary.

    Raises:
        NRLXCacheError: If the index file is missing or invalid.
    
    
    """
    info = get_cache_info(cache_root)

    if not info.index_file.exists():
        raise NRLXCacheError(f"Cache index not found at {info.index_file}." 
                            "Run 'nrlx init-cache'.")

    try:
        return json.loads(info.index_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise NRLXCacheError(f"Invalid cache index: {info.index_file}") from exc
    except OSError as exc:
        raise NRLXCacheError(f"Failed to read cache index: {info.index_file}") from exc

def _build_empty_index() -> dict[str, Any]:
    """Build an empty cache index payload.

    Returns:
        Dictionary containing cache metadata.
    
    
    """
    now = datetime.now(timezone.utc).isoformat()

    return {
        "schema_version": 1,
        "created_at_utc": now,
        "updated_at_utc": now,
        "nrl_version": None,
        "source": None,
        "entries": {}
    }