"""The library entry point: the catalog, its code table and the service"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import msgspec
from obspy import Inventory

from nrlx.core.combine import cascade_instconfig, combine_params
from nrlx.io.cache import (
    decode_catalog,
    decode_prefixes,
    get_catalog_file,
    get_prefixes_file,
    read_catalog,
    read_prefixes,
    write_catalog,
    write_prefixes,
)
from nrlx.io.inventory import label_channels, read_stationxml, set_coordinates
from nrlx.io.service import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, get
from nrlx.models.catalog import Catalog, Found
from nrlx.schema.prefixes import PrefixInput
from nrlx.schema.response import ResponseInput


class Nrlx(msgspec.Struct, frozen=True, kw_only=True):
    """The NRL catalog, its code table and the service, to find and build responses

    Args:
        catalog: catalog to resolve the selections.
        prefixes: codes of the instconfig parameters, for the conditions on the
            parameters (FR=40). Empty when not loaded.
        base_url: base URL of the NRL service.
        timeout: timeout of the requests in seconds.


    """

    catalog: Catalog
    prefixes: list[PrefixInput] = []
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_cache(
        cls,
        cache_root: Path | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ) -> Nrlx:
        """Load the catalog and the code table already in the cache, without requests

        Args:
            cache_root: custom root folder of the cache, None for the platform cache
                folder of the user.
            base_url: base URL of the NRL service.

        Returns:
            Nrlx with the catalog and the code table of the cache.

        Raises:
            FileNotFoundError: if the catalog or the code table has not been synced
                yet (the caches synced before nrlx 0.3 have no code table).
            ValueError: if the catalog or the code table is not valid.
            OSError: if a file cannot be read.


        """
        catalog = read_catalog(get_catalog_file(cache_root))
        prefixes = read_prefixes(get_prefixes_file(cache_root))
        nrl = cls(catalog=catalog, prefixes=prefixes, base_url=base_url)

        return nrl

    @classmethod
    def sync(
        cls,
        cache_root: Path | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ) -> Nrlx:
        """Download the current catalog and code table in the cache, then load them

        Both are validated before either is written, so a broken download leaves the
        previous files in the cache, together. Safe on a fresh machine and to
        refresh.

        Args:
            cache_root: custom root folder of the cache, None for the platform cache
                folder of the user.
            base_url: base URL of the NRL service.

        Returns:
            Nrlx with the downloaded catalog and code table.

        Raises:
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.
            ValueError: if the download is not a valid catalog or code table.
            OSError: if the files cannot be written.


        """
        catalogcontent = get(base_url, "catalog")
        prefixescontent = get(
            base_url, "prefix-lookup", {"format": "json", "nodata": 404}
        )

        # both validated before replacing the previous files
        try:
            catalog = decode_catalog(catalogcontent)
        except msgspec.DecodeError as err:
            raise ValueError(f"Invalid catalog from {base_url}. {err}") from err
        try:
            prefixes = decode_prefixes(prefixescontent)
        except msgspec.DecodeError as err:
            raise ValueError(f"Invalid code table from {base_url}. {err}") from err
        write_catalog(catalogcontent, get_catalog_file(cache_root))
        write_prefixes(prefixescontent, get_prefixes_file(cache_root))

        nrl = cls(catalog=catalog, prefixes=prefixes, base_url=base_url)

        return nrl

    def find(self, keys: list[str], element: str | None = None) -> Found:
        """Configurations matched by keys, see Catalog.find

        Args:
            keys: words (luni, LP1) and conditions (FR=40, corner>=60), all of them.
            element: element searched, for example sensor; None for every element.

        Returns:
            the matched rows, the parameters that still vary, the notes and the
            hints.

        Raises:
            ValueError: if a condition name stands for several parameters, or a
                range has no bound.


        """
        found = self.catalog.find(keys, self.prefixes, element)

        return found

    def response(
        self,
        *,
        sensor: list[str] | None = None,
        datalogger: list[str] | None = None,
        integrated: list[str] | None = None,
        soh: list[str] | None = None,
        network: str | None = None,
        station: str | None = None,
        location: str | None = None,
        channels: list[str] | None = None,
        starttime: datetime | None = None,
        endtime: datetime | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        elevation: float = 0.0,
        depth: float = 0.0,
    ) -> Inventory:
        """Response of the parts, with a channel for each code, in an Inventory

        Each part is resolved in the catalog before the request, so that a part
        matching no configuration or several fails without network. The service
        builds the response once; each channel code is a copy of it, and the labels
        and the place are set on them. See ResponseInput for the arguments.

        Args:
            sensor: keys of the sensor, None without a sensor.
            datalogger: keys of the datalogger, None without a datalogger.
            integrated: keys of the integrated instrument, None without one.
            soh: keys of the state of health channel, None without one.
            network: network code, None for the service placeholder.
            station: station code, None for the service placeholder.
            location: location code, None for the service placeholder.
            channels: channel codes, written as given; None for a single channel
                with the service placeholder.
            starttime: start of the validity, UTC; None for the service
                placeholder.
            endtime: end of the validity, UTC; None for no end.
            latitude: latitude of the station in degrees, None for the service
                placeholder.
            longitude: longitude in degrees, given with the latitude.
            elevation: elevation in metres, with the coordinates.
            depth: depth of the sensors below the surface in metres, with the
                coordinates.

        Returns:
            obspy inventory with the channels.

        Raises:
            ValueError: if the request is invalid (see ResponseInput), or a
                condition name stands for several parameters.
            LookupError: if a part matches no configuration, or more than one.
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.


        """
        request = ResponseInput(
            sensor=sensor,
            datalogger=datalogger,
            integrated=integrated,
            soh=soh,
            network=network,
            station=station,
            location=location,
            channels=channels or [],
            starttime=starttime,
            endtime=endtime,
            latitude=latitude,
            longitude=longitude,
            elevation=elevation,
            depth=depth,
        )

        # the exact instconfigs, in the order of the signal, before any request
        instconfigs = [
            self.catalog.resolve(element, keys, self.prefixes).instconfig
            for element, keys in [
                ("sensor", request.sensor),
                ("datalogger", request.datalogger),
                ("integrated", request.integrated),
                ("soh", request.soh),
            ]
            if keys is not None
        ]
        params = combine_params(cascade_instconfig(instconfigs))
        content = get(self.base_url, "combine", params, self.timeout)

        # a channel for each code, labelled, then placed
        inventory = label_channels(
            read_stationxml(content),
            request.network,
            request.station,
            request.location,
            request.channels,
            request.starttime,
            request.endtime,
        )
        if request.latitude is not None and request.longitude is not None:
            inventory = set_coordinates(
                inventory,
                request.latitude,
                request.longitude,
                request.elevation,
                request.depth,
            )

        return inventory
