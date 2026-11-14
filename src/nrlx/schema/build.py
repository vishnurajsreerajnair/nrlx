"""Structs of the request of a response built by the NRL service"""

from __future__ import annotations

from collections import Counter

import msgspec

from nrlx.models.instrument import Instrument
from nrlx.schema.response import ResponseFormat


class BuildInput(
    msgspec.Struct,
    kw_only=True,
    forbid_unknown_fields=True,
    frozen=True,
):
    """Request of the responses of a sensor, and datalogger, for some channels

    The /combine endpoint labels a single channel for each request, so each channel
    code is a response: written in its own file, or merged in a single stationxml.

    Args:
        sensor: selection of the sensor configuration.
        datalogger: selection of the datalogger configuration, cascaded after the
            sensor. None for the response of the sensor alone.
        format: format of the responses.
        compress: whether to request the responses as zip archives.
        network: network code of the responses, None for the service placeholder.
        station: station code of the responses, None for the service placeholder.
        location: location code of the responses, None for the service placeholder.
        channels: channel codes, a response for each of them. Empty for a single
            response with the service placeholder.
        merge_channels: whether to merge the responses of the channels in a single
            stationxml.
        starttime: start of the validity of the responses, None for the service
            placeholder.
        endtime: end of the validity of the responses, None for the service
            placeholder.
        latitude: latitude of the station in degrees, stamped on the station and its
            channels; None for the service placeholder.
        longitude: longitude of the station in degrees, given with the latitude.
        elevation: elevation of the station in metres, with the coordinates.
        depth: depth of the sensors below the surface in metres, with the
            coordinates.


    """

    sensor: Instrument
    datalogger: Instrument | None = None
    format: ResponseFormat = "stationxml"
    compress: bool = False
    network: str | None = None
    station: str | None = None
    location: str | None = None
    channels: list[str] = []
    merge_channels: bool = False
    starttime: str | None = None
    endtime: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation: float = 0.0
    depth: float = 0.0

    def __post_init__(self) -> None:
        # a channel requested twice would be written twice
        repeated = [
            channel for channel, count in Counter(self.channels).items() if count > 1
        ]
        if repeated:
            raise ValueError(f"The channels must be unique. Repeated {repeated}")

        # the merged stationxml holds the channels of at least two responses, read
        # by obspy
        if self.merge_channels and len(self.channels) < 2:
            raise ValueError(
                "Merging the channels needs at least two channels. "
                f"Provided {self.channels}"
            )
        if self.merge_channels and (self.format != "stationxml" or self.compress):
            raise ValueError(
                "Merging the channels needs the stationxml format, not zipped. "
                f"Provided format {self.format}, compress {self.compress}"
            )

        # the coordinates come together, in range, and only in a stationxml
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "The latitude and the longitude go together. "
                f"Provided latitude {self.latitude}, longitude {self.longitude}"
            )
        if self.latitude is None and (self.elevation != 0.0 or self.depth != 0.0):
            raise ValueError(
                "The elevation and the depth need the latitude and the longitude. "
                f"Provided elevation {self.elevation}, depth {self.depth}"
            )
        if self.latitude is not None and not -90.0 <= self.latitude <= 90.0:
            raise ValueError(
                f"The latitude must be within ±90°. Provided {self.latitude}"
            )
        if self.longitude is not None and not -180.0 <= self.longitude <= 180.0:
            raise ValueError(
                f"The longitude must be within ±180°. Provided {self.longitude}"
            )
        if self.depth < 0.0:
            raise ValueError(f"The depth must not be negative. Provided {self.depth}")
        if self.latitude is not None and (self.format != "stationxml" or self.compress):
            raise ValueError(
                "The coordinates need the stationxml format, not zipped. "
                f"Provided format {self.format}, compress {self.compress}"
            )
