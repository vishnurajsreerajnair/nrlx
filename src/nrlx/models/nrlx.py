"""The library entry point: the catalog, its code table and the service"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import msgspec
from obspy import Inventory
from obspy.core.inventory.response import Response

from nrlx.core.combine import (
    cascade_instconfig,
    combine_params,
    combine_responses,
    output_rate,
    received_notes,
)
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
from nrlx.io.inventory import (
    label_channels,
    placeholder_inventory,
    read_part,
    read_stationxml,
    set_coordinates,
)
from nrlx.io.local import (
    DOWNLOAD_TIMEOUT,
    FULL_NRL_PARAMS,
    extract_tree,
    get_part_file,
    get_tree_dir,
    install_tree,
    missing_parts,
)
from nrlx.io.service import DEFAULT_BASE_URL, DEFAULT_TIMEOUT, download, get
from nrlx.models.catalog import Catalog, Found
from nrlx.schema.prefixes import PrefixInput
from nrlx.schema.response import ResponseInput, Source


class Nrlx(msgspec.Struct, frozen=True, kw_only=True):
    """The NRL catalog, its code table and the service, to find and build responses

    Args:
        catalog: catalog to resolve the selections.
        prefixes: codes of the instconfig parameters, for the conditions on the
            parameters (FR=40). Empty when not loaded.
        base_url: base URL of the NRL service.
        timeout: timeout of the requests in seconds.
        local_tree: folder of the local copy of the NRL, None without one.


    """

    catalog: Catalog
    prefixes: list[PrefixInput] = []
    base_url: str = DEFAULT_BASE_URL
    timeout: float = DEFAULT_TIMEOUT
    local_tree: Path | None = None

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
            Nrlx with the catalog and the code table of the cache, and the local
            copy of the NRL when it has been synced.

        Raises:
            FileNotFoundError: if the catalog or the code table has not been synced
                yet (the caches synced before nrlx 0.3 have no code table).
            ValueError: if the catalog or the code table is not valid.
            OSError: if a file cannot be read.


        """
        catalog = read_catalog(get_catalog_file(cache_root))
        prefixes = read_prefixes(get_prefixes_file(cache_root))
        tree = get_tree_dir(cache_root)
        nrl = cls(
            catalog=catalog,
            prefixes=prefixes,
            base_url=base_url,
            local_tree=tree if tree.is_dir() else None,
        )

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

        tree = get_tree_dir(cache_root)
        nrl = cls(
            catalog=catalog,
            prefixes=prefixes,
            base_url=base_url,
            local_tree=tree if tree.is_dir() else None,
        )

        return nrl

    @classmethod
    def sync_local(
        cls,
        cache_root: Path | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ) -> tuple[Nrlx, list[str]]:
        """Download the whole NRL with the catalog and the code table, as the local
        copy

        The zip (about 300 MB) is unzipped beside the copy and checked against the
        catalog; then the tree, the catalog and the code table replace the
        previous ones together, and the zip is deleted. A failure before keeps the
        previous copy whole.

        Args:
            cache_root: custom root folder of the cache, None for the platform cache
                folder of the user.
            base_url: base URL of the NRL service.

        Returns:
            Nrlx with the local copy, and the notes on the configurations of the
            catalog without a file in the zip.

        Raises:
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.
            ValueError: if a download is not a valid catalog, code table or NRL
                zip.
            OSError: if the files cannot be written.


        """
        catalogcontent = get(base_url, "catalog")
        prefixescontent = get(
            base_url, "prefix-lookup", {"format": "json", "nodata": 404}
        )
        try:
            catalog = decode_catalog(catalogcontent)
        except msgspec.DecodeError as err:
            raise ValueError(f"Invalid catalog from {base_url}. {err}") from err
        try:
            prefixes = decode_prefixes(prefixescontent)
        except msgspec.DecodeError as err:
            raise ValueError(f"Invalid code table from {base_url}. {err}") from err

        # the zip and the new tree beside the copy, removed whatever happens
        tree = get_tree_dir(cache_root)
        tree.parent.mkdir(parents=True, exist_ok=True)
        zip_file = tree.with_name(f"{tree.name}.zip")
        staged = tree.with_name(f"{tree.name}.new")
        try:
            if staged.exists():
                shutil.rmtree(staged)
            download(base_url, "combine", FULL_NRL_PARAMS, zip_file, DOWNLOAD_TIMEOUT)
            extract_tree(zip_file, staged)
            instconfigs = [
                configuration.instconfig
                for *_, configuration in catalog.get_configurations()
            ]
            missing = missing_parts(staged, instconfigs)

            # the three together
            install_tree(staged, tree)
            write_catalog(catalogcontent, get_catalog_file(cache_root))
            write_prefixes(prefixescontent, get_prefixes_file(cache_root))
        finally:
            zip_file.unlink(missing_ok=True)
            if staged.exists():
                shutil.rmtree(staged)

        notes = [f"no file in the NRL zip: {instconfig}" for instconfig in missing]
        nrl = cls(
            catalog=catalog, prefixes=prefixes, base_url=base_url, local_tree=tree
        )

        return nrl, notes

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
        sensor_response: Response | None = None,
        datalogger_response: Response | None = None,
        source: Source = "service",
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
    ) -> tuple[Inventory, list[str]]:
        """Response of the parts, with a channel for each code, in an Inventory

        Each part is resolved in the catalog before the request, so that a part
        matching no configuration or several fails without network. With NRL parts
        only, the service builds the response; with a response from a file, the NRL
        part is asked alone and nrlx combines the two (see combine_responses).
        From the local copy, a part alone is its file and two parts are combined
        by nrlx, without any request. Each channel code is a copy of the response,
        and the labels and the place are set on them. See ResponseInput for the
        arguments.

        Args:
            sensor: keys of the sensor, None without a sensor.
            datalogger: keys of the datalogger, None without a datalogger.
            sensor_response: response of the sensor (or of a whole channel) in
                place of its keys, None to select it by keys.
            datalogger_response: response of the datalogger (or of a whole
                channel) in place of its keys, None to select it by keys.
            source: where the NRL parts come from, "service" or "local".
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
            obspy inventory with the channels, and the notes: on what the
            combination by nrlx filled or corrected, or on the response kept as
            received (see received_notes).

        Raises:
            ValueError: if the request is invalid (see ResponseInput), a condition
                name stands for several parameters, or the parts do not combine.
            LookupError: if a part matches no configuration, or more than one.
            FileNotFoundError: if the local copy, or the file of a part in it, is
                missing.
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.


        """
        request = ResponseInput(
            sensor=sensor,
            datalogger=datalogger,
            sensor_response=sensor_response,
            datalogger_response=datalogger_response,
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
            source=source,
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
        notes: list[str] = list()
        files = request.sensor_response is not None or (
            request.datalogger_response is not None
        )
        match (request.source, files, instconfigs):
            case ("service", False, _):
                # NRL parts only: the service combines them
                params = combine_params(cascade_instconfig(instconfigs))
                content = get(self.base_url, "combine", params, self.timeout)
                built = read_stationxml(content)
                notes = received_notes(built[0][0][0].response)
            case ("local", False, [instconfig]):
                # a part alone: its file, as the service gives it
                built = read_stationxml(self.local_file(instconfig).read_bytes())
                notes = received_notes(built[0][0][0].response)
            case _:
                # a sensor and a datalogger combined by nrlx: the sensor is the
                # first instconfig, the datalogger the last
                sensor_part = (
                    request.sensor_response
                    if request.sensor_response is not None
                    else self.part(instconfigs[0], request.source)
                )
                datalogger_part = (
                    request.datalogger_response
                    if request.datalogger_response is not None
                    else self.part(instconfigs[-1], request.source)
                )
                combined, notes = combine_responses(sensor_part, datalogger_part)
                built = placeholder_inventory(
                    combined, output_rate(combined.response_stages)
                )

        # a channel for each code, labelled, then placed
        inventory = label_channels(
            built,
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

        return inventory, notes

    def part(self, instconfig: str, source: Source = "service") -> Response:
        """Response of a single part of the NRL, from the service or the local copy

        Args:
            instconfig: exact instconfig of the part.
            source: "service" or "local".

        Returns:
            the response of its channel.

        Raises:
            FileNotFoundError: if the local copy, or the file of the part in it, is
                missing.
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.


        """
        match source:
            case "local":
                response = read_part(self.local_file(instconfig))
            case _:
                params = combine_params(cascade_instconfig([instconfig]))
                content = get(self.base_url, "combine", params, self.timeout)
                response = read_stationxml(content)[0][0][0].response

        return response

    def local_file(self, instconfig: str) -> Path:
        """File of a part in the local copy

        Args:
            instconfig: exact instconfig of the part.

        Returns:
            path of its file.

        Raises:
            FileNotFoundError: if there is no local copy, or the part has no file
                in it (synced before the catalog had the part).


        """
        if self.local_tree is None:
            raise FileNotFoundError("No local NRL copy: run 'nrlx local sync'.")
        part_file = get_part_file(self.local_tree, instconfig)
        if not part_file.is_file():
            raise FileNotFoundError(
                f"{instconfig} is not in the local NRL copy: run 'nrlx local sync'."
            )

        return part_file
