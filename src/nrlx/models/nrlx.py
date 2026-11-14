"""The library entry point: the catalog and the service, to build responses"""

from __future__ import annotations

from pathlib import Path

import msgspec

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
from nrlx.io.service import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, get
from nrlx.models.catalog import Catalog
from nrlx.models.instrument import Instrument
from nrlx.models.response import BuiltResponse
from nrlx.schema.prefixes import PrefixInput
from nrlx.schema.response import ResponseFormat


class Nrlx(msgspec.Struct, frozen=True, kw_only=True):
    """The NRL catalog and service, to find configurations and build responses

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

    def combine(
        self,
        *,
        sensor_instconfig: str | None = None,
        sensor_keys: list[str] | None = None,
        datalogger_instconfig: str | None = None,
        datalogger_keys: list[str] | None = None,
        format: ResponseFormat = "stationxml",
        compress: bool = False,
        network: str | None = None,
        station: str | None = None,
        location: str | None = None,
        channel: str | None = None,
        starttime: str | None = None,
        endtime: str | None = None,
    ) -> BuiltResponse:
        """Build the response of a sensor, and datalogger, in memory

        Each element is selected by an exact instconfig or by keys resolved in the
        catalog (see Catalog.get_configurations), one or the other. The datalogger is
        optional. The response is not written: see BuiltResponse.save, and the obspy
        conversions.

        Args:
            sensor_instconfig: exact instconfig of the sensor.
            sensor_keys: keys matching a single sensor configuration.
            datalogger_instconfig: exact instconfig of the datalogger.
            datalogger_keys: keys matching a single datalogger configuration.
            format: format of the response.
            compress: whether to request the response as a zip archive.
            network: network code, None for the service placeholder.
            station: station code, None for the service placeholder.
            location: location code, None for the service placeholder.
            channel: channel code, None for the service placeholder.
            starttime: start of the validity, None for the service placeholder.
            endtime: end of the validity, None for the service placeholder.

        Returns:
            the built response.

        Raises:
            ValueError: if an element has both an instconfig and keys.
            LookupError: if the keys match no configuration, or more than one.
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.


        """
        # the exact instconfigs, resolved in the catalog before the request
        sensor = Instrument(instconfig=sensor_instconfig, keys=sensor_keys or [])
        sensorinstconfig = sensor.get_instconfig(self.catalog, "sensor")
        dataloggerinstconfig = None
        if datalogger_instconfig is not None or datalogger_keys:
            datalogger = Instrument(
                instconfig=datalogger_instconfig, keys=datalogger_keys or []
            )
            dataloggerinstconfig = datalogger.get_instconfig(self.catalog, "datalogger")

        instconfig = cascade_instconfig(sensorinstconfig, dataloggerinstconfig)
        params = combine_params(
            instconfig,
            format,
            compress,
            network,
            station,
            location,
            channel,
            starttime,
            endtime,
        )
        content = get(self.base_url, "combine", params, self.timeout)

        response = BuiltResponse(content, format, instconfig, compress)

        return response
