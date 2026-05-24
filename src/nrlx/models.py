from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CacheInfo:
    """Information about the local nrlx cache.

    Args:
        root: Root cache directory used by nrlx.
        nrl_dir: Directory reserved for NRL data.
        index_file: Path to the local cache index file.
        exists: Whether the cache root already exists.
    
    
    """
    root: Path
    nrl_dir: Path
    index_file: Path
    exists: bool