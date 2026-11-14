"""Selection of a sensor or datalogger configuration, resolved in the catalog"""

from __future__ import annotations

from nrlx.models.catalog import Catalog
from nrlx.schema.instrument import InstrumentInput


class Instrument(InstrumentInput, frozen=True):
    def get_instconfig(self, catalog: Catalog, element_name: str) -> str:
        """instconfig of the selected configuration

        The exact instconfig is used as it is, without looking it up in the catalog;
        the filters must match a single configuration of the catalog.

        Args:
            catalog: catalog to match the filters.
            element_name: element of the configuration, sensor or datalogger.

        Returns:
            exact instconfig.

        Raises:
            LookupError: if no configuration matches the filters, or more than one.


        """
        instconfig = self.instconfig
        if instconfig is None:
            instconfig = catalog.resolve(
                element_name,
                manufacturer_name=self.manufacturer,
                model_name=self.model,
                keys=self.keys,
            ).instconfig

        return instconfig
