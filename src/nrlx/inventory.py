"""ObsPy-backed conversions for built responses.

Everything here needs ``obspy`` (the ``nrlx[obspy]`` extra); the rest of nrlx
does not. The import happens inside ``_load_obspy`` so this module - and
anything importing it - stays importable without obspy installed. Callers get
a clear install hint the moment they actually use a converter.


"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

from nrlx.exceptions import NrlxError

_OBSPY_HINT = (
    "This operation needs obspy. Install it with: pip install 'nrlx[obspy]'"
)


def _load_obspy() -> Any:
    """Import and return the obspy module, or raise a clear install hint."""
    try:
        import obspy
    except ImportError as exc:
        raise NrlxError(_OBSPY_HINT) from exc
    return obspy


def inventory_from_stationxml(data: bytes) -> Any:
    """Parse StationXML bytes into an ``obspy.Inventory``, entirely in memory.

    Args:
        data: StationXML document bytes (e.g. ``BuiltResponse.content``).

    Returns:
        obspy.core.inventory.inventory.Inventory

    Raises:
        NrlxError: If obspy is not installed.


    """
    obspy = _load_obspy()
    return obspy.read_inventory(io.BytesIO(data))


def response_from_stationxml(data: bytes) -> Any:
    """Extract the bare ``obspy Response`` from single-channel StationXML bytes.

    The returned Response carries no network/station/channel codes, so it can
    be attached to channels you build yourself with any naming you like.

    Args:
        data: StationXML document bytes containing one channel.

    Returns:
        obspy.core.inventory.response.Response

    Raises:
        NrlxError: If obspy is not installed.


    """
    inventory = inventory_from_stationxml(data)
    return inventory[0][0][0].response


def merge_stationxml(blobs: Sequence[bytes]) -> bytes:
    """Merge single-channel StationXML documents into one multi-channel one.

    All inputs are expected to share the same network/station codes (as the
    per-channel outputs of one ``nrlx build`` run do); the channels of every
    document after the first are appended to the first document's station.

    Args:
        blobs: StationXML documents, one channel each.

    Returns:
        A single StationXML document containing every channel.

    Raises:
        NrlxError: If obspy is not installed.


    """
    obspy = _load_obspy()

    inventories = [obspy.read_inventory(io.BytesIO(blob)) for blob in blobs]
    merged = inventories[0]
    station = merged[0][0]

    for extra in inventories[1:]:
        station.channels.extend(extra[0][0].channels)

    station.total_number_of_channels = len(station.channels)
    station.selected_number_of_channels = len(station.channels)

    buffer = io.BytesIO()
    merged.write(buffer, format="STATIONXML")
    return buffer.getvalue()
