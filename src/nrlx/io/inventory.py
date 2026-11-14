"""Reading of responses with obspy, and labelling and placing of their channels"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from obspy import Inventory, UTCDateTime, read_inventory
from obspy.core.inventory import Channel, Network, Station
from obspy.core.inventory.response import Response

# the start of the validity in the placeholders of the NRL service
PLACEHOLDER_START = UTCDateTime(1970, 1, 1)


def read_stationxml(content: bytes) -> Inventory:
    """Read a StationXML document in memory

    Args:
        content: StationXML document.

    Returns:
        obspy inventory of the document.


    """
    inventory = read_inventory(io.BytesIO(content), format="STATIONXML")

    return inventory


def read_part(path: Path, seed_id: str | None = None) -> Response:
    """Response of a channel in a file, to use as a part of a combination

    Any format obspy reads (StationXML, RESP, dataless SEED). Without seed_id the
    file must hold a single channel.

    Args:
        path: file of the response.
        seed_id: NET.STA.LOC.CHA of the channel, None for the only one.

    Returns:
        the response of the channel.

    Raises:
        OSError: if the file cannot be read.
        ValueError: if obspy cannot read the format, or the channel has no
            response.
        LookupError: if no channel or several match.


    """
    try:
        inventory = read_inventory(str(path))
    except TypeError as err:
        # obspy's error for an unknown format
        raise ValueError(f"Cannot read {path}: {err}") from err
    channels = [
        (f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}", cha)
        for net in inventory
        for sta in net
        for cha in sta
    ]
    matched = [cha for code, cha in channels if seed_id is None or code == seed_id]
    ids = ", ".join(sorted({code for code, _ in channels})) or "none"
    match matched:
        case [channel] if channel.response is not None:
            response = channel.response
        case [_]:
            raise ValueError(f"The channel {seed_id or ids} of {path} has no response.")
        case []:
            raise LookupError(f"No channel {seed_id} in {path} (channels: {ids}).")
        case _:
            raise LookupError(
                f"{path} has {len(matched)} channels or epochs: pick one with "
                f"FILE#NET.STA.LOC.CHA (channels: {ids})."
            )

    return response


def placeholder_inventory(response: Response, sample_rate: float | None) -> Inventory:
    """Inventory of a single channel with the placeholders of the NRL service,
    XX.YY.00.ZZZ from 1970-01-01, around a response combined by nrlx

    So that label_channels and set_coordinates work on it as on an answer of the
    service.

    Args:
        response: response of the channel.
        sample_rate: output rate of the response, None without digital stages.

    Returns:
        the inventory.


    """
    channel = Channel(
        "ZZZ",
        "00",
        0.0,
        0.0,
        0.0,
        0.0,
        azimuth=0.0,
        dip=0.0,
        sample_rate=sample_rate,
        start_date=PLACEHOLDER_START,
        response=response,
    )
    station = Station("YY", 0.0, 0.0, 0.0, [channel], start_date=PLACEHOLDER_START)
    network = Network("XX", [station], start_date=PLACEHOLDER_START)
    inventory = Inventory([network], source="nrlx")

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
