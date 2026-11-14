"""Reading of StationXML responses with obspy, and labelling of their channels"""

from __future__ import annotations

import io
from datetime import datetime

from obspy import Inventory, UTCDateTime, read_inventory


def read_stationxml(content: bytes) -> Inventory:
    """Read a StationXML document in memory

    Args:
        content: StationXML document.

    Returns:
        obspy inventory of the document.


    """
    inventory = read_inventory(io.BytesIO(content), format="STATIONXML")

    return inventory


def label_channels(
    inventory: Inventory,
    network: str | None,
    station: str | None,
    location: str | None,
    channels: list[str],
    starttime: datetime | None,
    endtime: datetime | None,
) -> Inventory:
    """Copy of a response of the NRL service with the labels of its channels

    The service answers a network with a station and a channel; each channel code
    is a copy of that channel. The labels not given keep the service placeholders.

    Args:
        inventory: response of the service, a single channel.
        network: network code, None to keep the placeholder.
        station: station code, None to keep the placeholder.
        location: location code, None to keep the placeholder.
        channels: channel codes, a copy of the channel each; empty to keep the
            single channel with its placeholder.
        starttime: start of the validity, UTC; None to keep the placeholder.
        endtime: end of the validity, UTC; None for no end.

    Returns:
        the labelled inventory; the given one is not changed.


    """
    labelled = inventory.copy()
    start = UTCDateTime(starttime) if starttime is not None else None
    end = UTCDateTime(endtime) if endtime is not None else None

    for net in labelled:
        # the network and its validity
        net.code = network if network is not None else net.code
        net.start_date = start if start is not None else net.start_date
        net.end_date = end
        for sta in net:
            # a copy of the channel of the service for each channel code
            template = sta.channels[0]
            copies = [template.copy() for _ in channels] or [template]
            for channel, code in zip(copies, channels or [template.code], strict=True):
                channel.code = code
                channel.location_code = (
                    location if location is not None else channel.location_code
                )
                channel.start_date = start if start is not None else channel.start_date
                channel.end_date = end
            sta.channels = copies
            sta.code = station if station is not None else sta.code
            sta.start_date = start if start is not None else sta.start_date
            sta.end_date = end
            sta.total_number_of_channels = len(copies)
            sta.selected_number_of_channels = len(copies)

    return labelled


def set_coordinates(
    inventory: Inventory,
    latitude: float,
    longitude: float,
    elevation: float,
    depth: float,
) -> Inventory:
    """Copy of an inventory with the place of its stations and channels

    Args:
        inventory: inventory of a response.
        latitude: latitude of the station in degrees.
        longitude: longitude of the station in degrees.
        elevation: elevation of the station in metres.
        depth: depth of the sensors below the surface in metres.

    Returns:
        the placed inventory; the given one is not changed.


    """
    placed = inventory.copy()

    # the same place for the station and every channel, the depth only on channels
    for network in placed:
        for station in network:
            station.latitude = latitude
            station.longitude = longitude
            station.elevation = elevation
            for channel in station:
                channel.latitude = latitude
                channel.longitude = longitude
                channel.elevation = elevation
                channel.depth = depth

    return placed
