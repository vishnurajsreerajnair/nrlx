"""Requests to the /combine endpoint, which builds the responses"""

from __future__ import annotations

from nrlx.schema.response import ResponseFormat


def cascade_instconfig(
    sensor_instconfig: str, datalogger_instconfig: str | None
) -> str:
    """instconfig of the sensor, cascaded with the datalogger when given

    The /combine endpoint cascades the responses of the instconfigs joined by a colon
    in a single channel: this is the service contract, not an nrlx convention.

    Args:
        sensor_instconfig: exact instconfig of the sensor.
        datalogger_instconfig: exact instconfig of the datalogger, None for the
            sensor alone.

    Returns:
        instconfig of the response.


    """
    instconfig = sensor_instconfig
    if datalogger_instconfig is not None:
        instconfig = f"{sensor_instconfig}:{datalogger_instconfig}"

    return instconfig


def combine_params(
    instconfig: str,
    format: ResponseFormat,
    compress: bool,
    network: str | None,
    station: str | None,
    location: str | None,
    channel: str | None,
    starttime: str | None,
    endtime: str | None,
) -> dict[str, str | int]:
    """Query parameters of the /combine endpoint

    The codes and the validity window are sent only when given: the service fills
    in placeholders for the others. A missing response is a 404 error instead of an
    empty answer.

    Args:
        instconfig: instconfig of the response, see cascade_instconfig.
        format: format of the response.
        compress: whether to request the response as a zip archive.
        network: network code, None for the service placeholder.
        station: station code, None for the service placeholder.
        location: location code, None for the service placeholder.
        channel: channel code, None for the service placeholder.
        starttime: start of the validity, None for the service placeholder.
        endtime: end of the validity, None for the service placeholder.

    Returns:
        query parameters, by name.


    """
    # the zip archives have the .zip suffix in the format
    params: dict[str, str | int] = {
        "instconfig": instconfig,
        "format": f"{format}.zip" if compress else format,
        "nodata": 404,
    }

    # the codes and the window only when given
    optional = {
        "network": network,
        "station": station,
        "location": location,
        "channel": channel,
        "starttime": starttime,
        "endtime": endtime,
    }
    params.update(
        {name: value for name, value in optional.items() if value is not None}
    )

    return params
