"""Requests to the /combine endpoint, which builds the responses"""

from __future__ import annotations


def cascade_instconfig(instconfigs: list[str]) -> str:
    """instconfig of a response: the instconfigs of its parts, cascaded

    The /combine endpoint cascades the responses of the instconfigs joined by a colon
    in a single channel, the sensor before the datalogger: this is the service
    contract, not an nrlx convention.

    Args:
        instconfigs: exact instconfigs of the parts, in the order of the signal.

    Returns:
        instconfig of the response.


    """
    instconfig = ":".join(instconfigs)

    return instconfig


def combine_params(instconfig: str) -> dict[str, str | int]:
    """Query parameters of the /combine endpoint, for a StationXML response

    The labels and the place of the channels are set by nrlx afterwards, so the
    request asks only the response; a missing response is a 404 error instead of an
    empty answer.

    Args:
        instconfig: instconfig of the response, see cascade_instconfig.

    Returns:
        query parameters, by name.


    """
    params: dict[str, str | int] = {
        "instconfig": instconfig,
        "format": "stationxml",
        "nodata": 404,
    }

    return params
