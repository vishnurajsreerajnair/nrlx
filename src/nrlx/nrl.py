"""The nrlx entry point: find catalog configurations and build responses.

``Nrlx`` composes an :class:`nrlx.client.NRLClient` with a parsed
:class:`nrlx.catalog.Catalog`. ``resolve``/``resolve_sensor``/
``resolve_datalogger`` turn a human selection (manufacturer/model filters or
ObsPy-v1-style key lists) into an ``instconfig`` string; ``combine`` builds
the actual response from the ``/combine`` endpoint and returns it in memory
as a :class:`BuiltResponse`.


"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nrlx.cache import get_catalog_file
from nrlx.catalog import Catalog, Configuration, ElementKind
from nrlx.client import NRLClient
from nrlx.exceptions import NrlxError, NrlxResponseError
from nrlx.formats import ResponseFormat
from nrlx.inventory import inventory_from_stationxml, response_from_stationxml

# ResponseFormat is re-exported so `from nrlx.nrl import ResponseFormat` keeps
# working; the type itself lives in nrlx.formats to keep offline consumers off
# the network stack.
__all__ = ["Nrlx", "BuiltResponse", "ResponseFormat"]

MAX_CANDIDATES_SHOWN = 20


@dataclass(frozen=True)
class BuiltResponse:
    """A response built by the NRL service, held in memory.

    Args:
        content: Raw response bytes in ``format``.
        format: The format the response was requested in.
        instconfig: The (possibly colon-joined) instconfig it was built from.
        compressed: Whether ``content`` is a zip archive.


    """
    content: bytes
    format: ResponseFormat
    instconfig: str
    compressed: bool = False

    def save(self, output_file: Path | str) -> Path:
        """Write the response content to a local file.

        Args:
            output_file: Destination file path.

        Returns:
            Path to the written file.

        Raises:
            NrlxError: If the file cannot be written.


        """
        path = Path(output_file)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.content)
        except OSError as exc:
            raise NrlxError(f"Failed to write response file: {path}") from exc

        return path

    def to_inventory(self) -> Any:
        """Parse the response into an ``obspy.Inventory``, in memory.

        Returns:
            obspy.core.inventory.inventory.Inventory

        Raises:
            NrlxError: If obspy is not installed.
            NrlxResponseError: If the content is not plain StationXML.


        """
        self._require_stationxml()
        return inventory_from_stationxml(self.content)

    def to_response(self) -> Any:
        """Extract the bare ``obspy Response`` object, in memory.

        The Response carries no network/station/channel codes - attach it to
        channels you build yourself, with whatever naming you need. This is
        the NRL-v1-style workflow.

        Returns:
            obspy.core.inventory.response.Response

        Raises:
            NrlxError: If obspy is not installed.
            NrlxResponseError: If the content is not plain StationXML.


        """
        self._require_stationxml()
        return response_from_stationxml(self.content)

    def to_paz(self) -> Any:
        """Extract the poles-and-zeros stage of the response.

        Returns:
            obspy.core.inventory.response.PolesZerosResponseStage

        Raises:
            NrlxError: If obspy is not installed.
            NrlxResponseError: If the content is not plain StationXML.


        """
        return self.to_response().get_paz()

    def _require_stationxml(self) -> None:
        """Guard: the obspy converters only understand plain StationXML."""
        if self.format is not ResponseFormat.STATIONXML or self.compressed:
            raise NrlxResponseError(
                "In-memory conversion needs an uncompressed stationxml response; "
                f"this one is '{self.format.value}'"
                f"{' (zipped)' if self.compressed else ''}. "
                "Build with format=ResponseFormat.STATIONXML and compress=False."
            )


@dataclass(frozen=True)
class Nrlx:
    """Find NRL catalog configurations and build instrument responses.

    Args:
        client: HTTP client for the NRL web service.
        catalog: Parsed local NRL catalog.


    """
    client: NRLClient
    catalog: Catalog

    @classmethod
    def from_cache(
        cls,
        cache_root: Path | None = None,
        *,
        base_url: str | None = None,
    ) -> Nrlx:
        """Build an Nrlx instance from the locally cached catalog.

        Args:
            cache_root: Custom cache root; defaults to the platform user cache dir.
            base_url: Optional custom NRL service base URL.

        Returns:
            Nrlx configured with the cached catalog and a service client.

        Raises:
            NrlxCacheError: If the local catalog file is missing or invalid.


        """
        catalog = Catalog.from_file(get_catalog_file(cache_root))
        client = NRLClient.for_base_url(base_url)

        return cls(client=client, catalog=catalog)

    def resolve(
        self,
        kind: ElementKind | str,
        *,
        manufacturer: str | None = None,
        model: str | None = None,
        instconfig: str | None = None,
        keys: Sequence[str] | None = None,
    ) -> Configuration:
        """Resolve a single catalog configuration matching the given filters.

        Args:
            kind: Element kind to resolve, ``sensor`` or ``datalogger``.
            manufacturer: Optional manufacturer name filter.
            model: Optional model name filter.
            instconfig: Optional instconfig substring filter.
            keys: Optional ObsPy-v1-style key list - unordered, case-insensitive
                substrings that must ALL match somewhere in the configuration
                (manufacturer, model, instconfig, description, or a parameter
                value). Add keys until the selection is unique.

        Returns:
            The single matching Configuration.

        Raises:
            NrlxResponseError: If no configuration matches, or more than one does.


        """
        element = kind.value if isinstance(kind, ElementKind) else kind
        matches = self.catalog.configurations(
            element=element,
            manufacturer=manufacturer,
            model=model,
            instconfig=instconfig,
        )

        if keys:
            matches = tuple(
                c for c in matches if all(c.matches(key) for key in keys)
            )

        if not matches:
            raise NrlxResponseError(
                f"No {element} configuration found for the given filters."
            )

        if len(matches) > 1:
            shown = matches[:MAX_CANDIDATES_SHOWN]
            # One candidate per line: these are long strings, and a comma-run
            # wall is unreadable in both terminals and tracebacks.
            candidates = "\n".join(f"  {c.instconfig}" for c in shown)
            remaining = len(matches) - len(shown)
            suffix = f"\n  ...and {remaining} more" if remaining else ""
            raise NrlxResponseError(
                f"Ambiguous {element} selection: {len(matches)} configurations "
                f"match the given filters. Candidates:\n{candidates}{suffix}"
            )

        return matches[0]

    def resolve_sensor(
        self,
        *,
        manufacturer: str | None = None,
        model: str | None = None,
        instconfig: str | None = None,
        keys: Sequence[str] | None = None,
    ) -> Configuration:
        """Resolve a single sensor configuration matching the given filters."""
        return self.resolve(
            ElementKind.SENSOR,
            manufacturer=manufacturer,
            model=model,
            instconfig=instconfig,
            keys=keys,
        )

    def resolve_datalogger(
        self,
        *,
        manufacturer: str | None = None,
        model: str | None = None,
        instconfig: str | None = None,
        keys: Sequence[str] | None = None,
    ) -> Configuration:
        """Resolve a single datalogger configuration matching the given filters."""
        return self.resolve(
            ElementKind.DATALOGGER,
            manufacturer=manufacturer,
            model=model,
            instconfig=instconfig,
            keys=keys,
        )

    def combine(
        self,
        *,
        sensor_instconfig: str | None = None,
        sensor_keys: Sequence[str] | None = None,
        datalogger_instconfig: str | None = None,
        datalogger_keys: Sequence[str] | None = None,
        format: ResponseFormat = ResponseFormat.STATIONXML,
        compress: bool = False,
        network: str | None = None,
        station: str | None = None,
        location: str | None = None,
        channel: str | None = None,
        starttime: str | None = None,
        endtime: str | None = None,
    ) -> BuiltResponse:
        """Build a sensor(+datalogger) response and return it in memory.

        Select the sensor with an exact ``sensor_instconfig`` OR with
        ``sensor_keys`` (resolved through the catalog); same for the optional
        datalogger. The result never touches disk - use ``.save()`` on the
        returned BuiltResponse when you want a file, or ``.to_response()`` /
        ``.to_inventory()`` / ``.to_paz()`` for in-memory obspy objects.

        Args:
            sensor_instconfig: Exact sensor instconfig string.
            sensor_keys: Key list resolving to exactly one sensor configuration.
            datalogger_instconfig: Exact datalogger instconfig string.
            datalogger_keys: Key list resolving to exactly one datalogger
                configuration.
            format: Output format for the response.
            compress: If True, request a zipped response.
            network: Together with station, location, and channel: the codes
                stamped into the output, plus the starttime/endtime validity
                window. All optional - the service fills in placeholders.

        Returns:
            BuiltResponse holding the raw response content.

        Raises:
            NrlxResponseError: If the sensor selection is missing/contradictory,
                or a key list resolves to zero or several configurations.
            NrlxNetworkError: If the request fails or returns an error status.


        """
        sensor = self._pick_instconfig(
            ElementKind.SENSOR, sensor_instconfig, sensor_keys, required=True
        )
        datalogger = self._pick_instconfig(
            ElementKind.DATALOGGER,
            datalogger_instconfig,
            datalogger_keys,
            required=False,
        )
        # mypy: required=True guarantees sensor is not None
        assert sensor is not None

        params = self._combine_params(
            sensor,
            datalogger,
            format=format,
            compress=compress,
            network=network,
            station=station,
            location=location,
            channel=channel,
            starttime=starttime,
            endtime=endtime,
        )
        content = self.client.get("combine", params=params).content

        return BuiltResponse(
            content=content,
            format=format,
            instconfig=str(params["instconfig"]),
            compressed=compress,
        )

    def _pick_instconfig(
        self,
        kind: ElementKind,
        instconfig: str | None,
        keys: Sequence[str] | None,
        *,
        required: bool,
    ) -> str | None:
        """Turn an instconfig-or-keys selection into one instconfig string."""
        if instconfig is not None and keys:
            raise NrlxResponseError(
                f"Give either {kind.value}_instconfig or {kind.value}_keys, not both."
            )
        if instconfig is not None:
            return instconfig
        if keys:
            return self.resolve(kind, keys=keys).instconfig
        if required:
            raise NrlxResponseError(
                f"combine() needs {kind.value}_instconfig or {kind.value}_keys."
            )
        return None

    @staticmethod
    def _combine_params(
        sensor_instconfig: str,
        datalogger_instconfig: str | None,
        *,
        format: ResponseFormat,
        compress: bool,
        network: str | None,
        station: str | None,
        location: str | None,
        channel: str | None,
        starttime: str | None,
        endtime: str | None,
    ) -> dict[str, Any]:
        """Build the ``/combine`` query parameters.

        Same arguments as ``combine()``, minus the key resolution - by the
        time we're here both instconfigs are exact strings.


        """
        # Colon-joining sensor and datalogger instconfigs is the real /combine
        # API contract for cascading two responses into one channel - not ours.
        instconfig = (
            sensor_instconfig
            if datalogger_instconfig is None
            else f"{sensor_instconfig}:{datalogger_instconfig}"
        )
        format_value = f"{format.value}.zip" if compress else format.value

        params: dict[str, Any] = {
            "instconfig": instconfig,
            "format": format_value,
            "nodata": 404,
        }

        optional_params = {
            "network": network,
            "station": station,
            "location": location,
            "channel": channel,
            "starttime": starttime,
            "endtime": endtime,
        }
        params.update(
            {key: value for key, value in optional_params.items() if value is not None}
        )

        return params
