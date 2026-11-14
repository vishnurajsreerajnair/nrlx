"""Structs of the request of a response, and the formats of the response files"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal

import msgspec

ResponseFormat = Literal["resp", "stationxml", "stationxml-resp"]


class ResponseInput(
    msgspec.Struct,
    kw_only=True,
    forbid_unknown_fields=True,
    frozen=True,
):
    """Request of a response: its parts, and the labels and place of its channels

    Each part is selected by keys (see Catalog.find): a sensor, a datalogger or
    both, an integrated instrument alone, or a state of health channel alone. The
    labels not given keep the placeholders of the NRL service.

    Args:
        sensor: keys of the sensor, None without a sensor.
        datalogger: keys of the datalogger, None without a datalogger.
        integrated: keys of the integrated instrument (sensor and datalogger in
            one), None without one.
        soh: keys of the state of health channel, None without one.
        network: network code of the channels, None for the service placeholder.
        station: station code of the channels, None for the service placeholder.
        location: location code of the channels, None for the service placeholder.
        channels: channel codes, a channel with the same response each, written
            as given. Empty for a single channel with the service placeholder.
        starttime: start of the validity of the channels, UTC; None for the
            service placeholder.
        endtime: end of the validity of the channels, UTC; None for no end.
        latitude: latitude of the station and its channels in degrees; None for
            the service placeholder.
        longitude: longitude in degrees, given with the latitude.
        elevation: elevation in metres, with the coordinates.
        depth: depth of the sensors below the surface in metres, with the
            coordinates.


    """

    sensor: list[str] | None = None
    datalogger: list[str] | None = None
    integrated: list[str] | None = None
    soh: list[str] | None = None
    network: str | None = None
    station: str | None = None
    location: str | None = None
    channels: list[str] = []
    starttime: datetime | None = None
    endtime: datetime | None = None
    latitude: float | None = None
    longitude: float | None = None
    elevation: float = 0.0
    depth: float = 0.0

    def __post_init__(self) -> None:
        # the parts given, each with keys, in an allowed combination
        selections = [
            ("sensor", self.sensor),
            ("datalogger", self.datalogger),
            ("integrated", self.integrated),
            ("soh", self.soh),
        ]
        parts = [name for name, keys in selections if keys is not None]
        empty = [name for name, keys in selections if keys is not None and not keys]
        if empty:
            raise ValueError(f"The keys of the parts must not be empty: {empty}")
        match parts:
            case ["sensor"] | ["datalogger"] | ["sensor", "datalogger"]:
                pass
            case ["integrated"] | ["soh"]:
                pass
            case []:
                raise ValueError(
                    "A response needs a part: a sensor, a datalogger, an integrated "
                    "instrument or a state of health channel"
                )
            case _:
                raise ValueError(
                    "The parts go as a sensor, a datalogger or both, an integrated "
                    f"instrument alone, or a state of health channel alone. "
                    f"Provided {parts}"
                )

        # a channel requested twice would be written twice
        repeated = [
            channel for channel, count in Counter(self.channels).items() if count > 1
        ]
        if repeated:
            raise ValueError(f"The channels must be unique. Repeated {repeated}")

        # the validity ends after it starts
        if (
            self.starttime is not None
            and self.endtime is not None
            and self.endtime <= self.starttime
        ):
            raise ValueError(
                "The end time must be after the start time. "
                f"Provided {self.starttime} to {self.endtime}"
            )

        # the coordinates come together and in range
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
