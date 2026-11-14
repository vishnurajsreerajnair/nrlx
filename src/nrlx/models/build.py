"""Request of the responses of some channels, built by the NRL service"""

from __future__ import annotations

from nrlx.core.combine import cascade_instconfig
from nrlx.io.inventory import merge_stationxml, set_coordinates
from nrlx.models.nrlx import Nrlx
from nrlx.models.response import BuiltResponse
from nrlx.schema.build import BuildInput


class Build(BuildInput, frozen=True):
    def build(self, nrl: Nrlx) -> list[tuple[str | None, BuiltResponse]]:
        """Build the responses of the channels with the NRL service

        The selections are resolved in the catalog before any request, so that an
        ambiguous selection fails without network. The /combine endpoint labels a
        channel for each request: a request for each channel code, or a single one
        with the service placeholder without channels. With coordinates, the
        station and its channels are placed in every StationXML.

        Args:
            nrl: catalog and service.

        Returns:
            channel code and response of each request, or a single response with all
            the channels (code None) when merged.

        Raises:
            LookupError: if a selection matches no configuration, or more than one.
            httpx.HTTPError: if the service cannot be reached or answers with an
                error status.


        """
        # the exact instconfigs, from the catalog before any request
        sensor_instconfig = self.sensor.get_instconfig(nrl.catalog, "sensor")
        datalogger_instconfig = None
        if self.datalogger is not None:
            datalogger_instconfig = self.datalogger.get_instconfig(
                nrl.catalog, "datalogger"
            )

        # a request for each channel code, a single one without channels
        channels: list[str | None] = [*self.channels] if self.channels else [None]
        responses = [
            (
                channel,
                nrl.combine(
                    sensor_instconfig=sensor_instconfig,
                    datalogger_instconfig=datalogger_instconfig,
                    format=self.format,
                    compress=self.compress,
                    network=self.network,
                    station=self.station,
                    location=self.location,
                    channel=channel,
                    starttime=self.starttime,
                    endtime=self.endtime,
                ),
            )
            for channel in channels
        ]

        # a single stationxml with the channels of all the responses
        if self.merge_channels:
            merged = BuiltResponse(
                merge_stationxml([response.content for _, response in responses]),
                self.format,
                cascade_instconfig(sensor_instconfig, datalogger_instconfig),
            )
            responses = [(None, merged)]

        # the place of the station, on every stationxml
        if self.latitude is not None and self.longitude is not None:
            responses = [
                (
                    channel,
                    BuiltResponse(
                        set_coordinates(
                            response.content,
                            self.latitude,
                            self.longitude,
                            self.elevation,
                            self.depth,
                        ),
                        response.format,
                        response.instconfig,
                    ),
                )
                for channel, response in responses
            ]

        return responses
