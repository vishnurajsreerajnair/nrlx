"""nrlx — NRL eXtended.

Browse EarthScope/IRIS's Nominal Response Library (NRL v2) and build seismic
instrument responses. The library entry points are re-exported here:
``from nrlx import Nrlx, Catalog, Found, write_resp``.


"""

from __future__ import annotations

from nrlx.io.resp import write_resp
from nrlx.models.catalog import Catalog, Found
from nrlx.models.nrlx import Nrlx
from nrlx.version import __version__

__all__ = ["Nrlx", "Catalog", "Found", "write_resp", "__version__"]
