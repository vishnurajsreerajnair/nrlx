"""A response built by the NRL service, with its conversions"""

from __future__ import annotations

from pathlib import Path

import msgspec
from obspy import Inventory
from obspy.core.inventory.response import PolesZerosResponseStage, Response

from nrlx.io.inventory import read_stationxml
from nrlx.schema.response import ResponseFormat


class BuiltResponse(msgspec.Struct, frozen=True):
    """A response built by the NRL service, held in memory

    Args:
        content: response in the format, as returned by the service.
        format: format of the response.
        instconfig: instconfig of the response, the sensor and datalogger ones joined
            by a colon.
        compressed: whether the content is a zip archive.


    """

    content: bytes
    format: ResponseFormat
    instconfig: str
    compressed: bool = False

    def save(self, output_file: Path | str) -> Path:
        """Write the response to a file, creating its folders

        Args:
            output_file: path of the file.

        Returns:
            path of the file.

        Raises:
            OSError: if the folders or the file cannot be written.


        """
        path = Path(output_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.content)

        return path

    def to_inventory(self) -> Inventory:
        """The response as obspy inventory, read in memory

        Returns:
            obspy inventory with the network, station and channel of the response.

        Raises:
            ValueError: if the response is not uncompressed StationXML.


        """
        # obspy reads the stationxml, not the other formats or the zip archives
        if self.format != "stationxml" or self.compressed:
            raise ValueError(
                "In-memory conversion needs an uncompressed stationxml response. "
                f"Provided format {self.format}, compressed {self.compressed}"
            )
        inventory = read_stationxml(self.content)

        return inventory

    def to_response(self) -> Response:
        """The bare obspy response, without network, station and channel codes

        The NRL v1 workflow: the response is attached to the channels built by the
        user, with any codes.

        Returns:
            obspy response of the channel.

        Raises:
            ValueError: if the response is not uncompressed StationXML.


        """
        response = self.to_inventory()[0][0][0].response

        return response

    def to_paz(self) -> PolesZerosResponseStage:
        """The poles and zeros stage of the response

        Returns:
            obspy poles and zeros stage.

        Raises:
            ValueError: if the response is not uncompressed StationXML.


        """
        paz = self.to_response().get_paz()

        return paz
