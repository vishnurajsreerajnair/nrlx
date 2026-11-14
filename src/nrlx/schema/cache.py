"""Structs of the files that nrlx keeps in its local cache"""

from __future__ import annotations

import msgspec

from nrlx.models.catalog import Catalog


class CatalogFileInput(msgspec.Struct, frozen=True):
    """The catalog file, as downloaded from the /catalog endpoint

    Args:
        catalog: the catalog, under the NRLCatalog key of the JSON.


    """

    catalog: Catalog = msgspec.field(name="NRLCatalog")
