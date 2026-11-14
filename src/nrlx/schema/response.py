"""Structs of the request of a response, and the formats of the response files"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Literal

import msgspec
from obspy.core.inventory.response import Response

ResponseFormat = Literal["resp", "stationxml"]

# where the NRL parts come from: the service, or the local copy
Source = Literal["service", "local"]


class ResponseInput(
    msgspec.Struct,
    kw_only=True,
    forbid_unknown_fields=True,
    frozen=True,
):
    """Request of a response: its parts, and the labels and place of its channels

    Each part is selected by keys (see Catalog.find): a sensor, a datalogger or
    both, an integrated instrument alone, or a state of health channel alone. The
    sensor and the datalogger can instead be responses read from files, combined by
    nrlx with the other part. The labels not given keep the placeholders of the NRL
    service.

    Args:
        sensor: keys of the sensor, None without a sensor.
        datalogger: keys of the datalogger, None without a datalogger.
        sensor_response: response of the sensor, or of a whole channel, in place
            of its keys; None to select it by keys.
        datalogger_response: response of the datalogger, or of a whole channel, in
            place of its keys; None to select it by keys.
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
        source: where the NRL parts come from, the service or the local copy.


    """

    sensor: list[str] | None = None
    datalogger: list[str] | None = None
    sensor_response: Response | None = None
    datalogger_response: Response | None = None
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
    source: Source = "service"

    def __post_init__(self) -> None:
        # a part by keys or by a response, not both
        if self.sensor is not None and self.sensor_response is not None:
            raise ValueError("The sensor is given by keys or by a response, not both.")
        if self.datalogger is not None and self.datalogger_response is not None:
            raise ValueError(
                "The datalogger is given by keys or by a response, not both."
            )

        # the parts given, each with keys or a response, in an allowed combination
        selections = [
            ("sensor", self.sensor, self.sensor_response),
            ("datalogger", self.datalogger, self.datalogger_response),
            ("integrated", self.integrated, None),
            ("soh", self.soh, None),
        ]
        empty = [name for name, keys, _ in selections if keys is not None and not keys]
        if empty:
            raise ValueError(f"The keys of the parts must not be empty: {empty}")
        parts = [
            name
            for name, keys, response in selections
            if keys is not None or response is not None
        ]
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

        # a response from a file is combined with the other part
        if (
            self.sensor_response is not None or self.datalogger_response is not None
        ) and parts != ["sensor", "datalogger"]:
            raise ValueError(
                "A response from a file is combined with the other part: give a "
                "sensor and a datalogger."
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
