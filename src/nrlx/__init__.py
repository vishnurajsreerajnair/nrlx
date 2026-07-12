"""nrlx — NRL eXtended.

Browse EarthScope/IRIS's Nominal Response Library (NRL v2) and build seismic
instrument responses. The main entry points are re-exported here:
``from nrlx import Nrlx, BuiltResponse, Catalog, ResponseFormat``.


"""

from __future__ import annotations

import importlib
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from nrlx.catalog import Catalog
    from nrlx.formats import ResponseFormat
    from nrlx.nrl import BuiltResponse, Nrlx

# Single source of truth for the version is pyproject.toml; read it back from
# the installed package metadata instead of duplicating the string here.
try:
    __version__ = version("nrlx")
except PackageNotFoundError:  # running from a source tree that isn't installed
    __version__ = "0.0.0+unknown"

__all__ = ["Nrlx", "BuiltResponse", "Catalog", "ResponseFormat", "__version__"]

# Lazy re-exports (PEP 562): `from nrlx import Nrlx` works without making
# every `import nrlx.<submodule>` drag in the whole network stack - offline
# consumers like nrlx.doctor stay httpx-free.
_LAZY_EXPORTS = {
    "Nrlx": "nrlx.nrl",
    "BuiltResponse": "nrlx.nrl",
    "Catalog": "nrlx.catalog",
    "ResponseFormat": "nrlx.formats",
}


def __getattr__(name: str) -> Any:
    if name in _LAZY_EXPORTS:
        module = importlib.import_module(_LAZY_EXPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module 'nrlx' has no attribute {name!r}")
