"""Reading and merging of StationXML responses with obspy"""

from __future__ import annotations

import io

from obspy import Inventory, read_inventory


def read_stationxml(content: bytes) -> Inventory:
    """Read a StationXML document in memory

    Args:
        content: StationXML document.

    Returns:
        obspy inventory of the document.


    """
    inventory = read_inventory(io.BytesIO(content), format="STATIONXML")

    return inventory


def merge_stationxml(contents: list[bytes]) -> bytes:
    """Merge single-channel StationXML documents in one with all the channels

    The documents share the network and station codes, as the responses of a build
    labelled with different channels: the channels of the documents after the first
    are added to the station of the first.

    Args:
        contents: StationXML documents, with a channel each.

    Returns:
        StationXML document with all the channels.


    """
    inventories = [read_stationxml(content) for content in contents]

    # the channels of the others in the station of the first
    merged = inventories[0]
    station = merged[0][0]
    for inventory in inventories[1:]:
        station.channels.extend(inventory[0][0].channels)
    station.total_number_of_channels = len(station.channels)
    station.selected_number_of_channels = len(station.channels)

    buffer = io.BytesIO()
    merged.write(buffer, format="STATIONXML")

    return buffer.getvalue()


def set_coordinates(
    content: bytes, latitude: float, longitude: float, elevation: float, depth: float
) -> bytes:
    """Set the place of the station and of its channels in a StationXML document

    Args:
        content: StationXML document of a build.
        latitude: latitude of the station in degrees.
        longitude: longitude of the station in degrees.
        elevation: elevation of the station in metres.
        depth: depth of the sensors below the surface in metres.

    Returns:
        StationXML document with the coordinates.


    """
    inventory = read_stationxml(content)

    # the same place for the station and every channel, the depth only on channels
    for network in inventory:
        for station in network:
            station.latitude = latitude
            station.longitude = longitude
            station.elevation = elevation
            for channel in station:
                channel.latitude = latitude
                channel.longitude = longitude
                channel.elevation = elevation
                channel.depth = depth

    buffer = io.BytesIO()
    inventory.write(buffer, format="STATIONXML")

    return buffer.getvalue()
