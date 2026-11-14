"""nrlx — NRL eXtended.

Browse EarthScope/IRIS's Nominal Response Library (NRL v2) and build seismic
instrument responses. The library entry points are re-exported here:
``from nrlx import Nrlx, BuiltResponse, Catalog, ResponseFormat``.


"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from nrlx.models.catalog import Catalog
from nrlx.models.nrlx import Nrlx
from nrlx.models.response import BuiltResponse
from nrlx.schema.response import ResponseFormat

# the version is set in pyproject.toml, read back from the installed package
try:
    __version__ = version("nrlx")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = ["Nrlx", "BuiltResponse", "Catalog", "ResponseFormat", "__version__"]
