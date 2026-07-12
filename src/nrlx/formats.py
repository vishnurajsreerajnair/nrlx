"""Response output formats offered by the NRL service.

Kept in its own module (no dependencies) so that offline consumers such
as ``nrlx.doctor`` can use ``ResponseFormat`` without importing the network
stack that ``nrlx.nrl`` pulls in.


"""
from __future__ import annotations

from enum import Enum


class ResponseFormat(str, Enum):
    """Output formats supported by the NRL ``/combine`` endpoint."""

    RESP = "resp"
    STATIONXML = "stationxml"
    STATIONXML_RESP = "stationxml-resp"
