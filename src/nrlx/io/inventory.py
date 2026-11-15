"""Reading of responses with obspy, and labelling and placing of their channels"""

from __future__ import annotations

import io
import math
import warnings
from datetime import datetime
from pathlib import Path

from obspy import Inventory, UTCDateTime, read_inventory
from obspy.core.inventory import Channel, Comment, Network, Station
from obspy.core.inventory.response import (
    PolesZerosResponseStage,
    PolynomialResponseStage,
    Response,
)

from nrlx.core.assets import PROVENANCE_SUBJECT
from nrlx.core.combine import output_rate
from nrlx.core.convert import (
    LOSSLESS_TOLERANCE,
    check_frequencies,
    pz_amplitude,
    relative_difference,
)
from nrlx.io.resp import write_resp
from nrlx.io.sacpz import read_sacpz
from nrlx.schema.response import ResponseFormat

# the start of the validity and the codes in the placeholders of the NRL service
PLACEHOLDER_START = UTCDateTime(1970, 1, 1)
PLACEHOLDER_NETWORK = "XX"
PLACEHOLDER_STATION = "YY"

# the input units SACPZ holds, converted to displacement (obspy's writer)
SACPZ_UNITS = ["M", "M/S", "M/SEC", "M/S**2", "M/SEC**2"]

# the poles and zeros SACPZ holds: analog, in rad/s or in Hz (obspy converts)
SACPZ_TRANSFER_TYPES = ["LAPLACE (RADIANS/SECOND)", "LAPLACE (HERTZ)"]


def read_stationxml(content: bytes) -> Inventory:
    """Read a StationXML document in memory

    Args:
        content: StationXML document.

    Returns:
        obspy inventory of the document.


    """
    inventory = read_inventory(io.BytesIO(content), format="STATIONXML")

    return inventory


def read_channels(path: Path, seed_id: str | None = None) -> Inventory:
    """Channels of a file, every one or those of a SEED id

    Any format obspy reads (StationXML, RESP, dataless SEED, XSEED, SC3ML).
    Stations with the same code and start date are merged, as obspy splits the
    channels of RESP, and a rate obspy reads as 0 from a RESP below 0.5 sps is
    the output rate of the decimations.

    Args:
        path: file of the responses.
        seed_id: NET.STA.LOC.CHA of the channels kept (each epoch), None for every
            channel.

    Returns:
        an inventory with the channels kept; the stations and networks without
        any are left out.

    Raises:
        OSError: if the file cannot be read.
        ValueError: if obspy cannot read the format.
        LookupError: if no channel has the SEED id.


    """
    try:
        inventory = read_inventory(str(path))
    except TypeError as err:
        # obspy's error for an unknown format
        raise ValueError(f"Cannot read {path}: {err}") from err
    # obspy reads each channel of a RESP file in a station of its own: one station
    # per code and start date (as text: obspy's dates are not hashable), with all
    # their channels
    for net in inventory:
        stations: dict[tuple[str, str], Station] = dict()
        for sta in net:
            key = (sta.code, str(sta.start_date))
            if key in stations:
                stations[key].channels += sta.channels
            else:
                stations[key] = sta
        net.stations = list(stations.values())

    # obspy reads the rate of a RESP file as an integer (input rate over the
    # decimation, rounded), so a channel below 0.5 sps reads 0: its rate is the
    # output of its last decimation
    for net in inventory:
        for sta in net:
            for cha in sta:
                if not cha.sample_rate and cha.response is not None:
                    cha.sample_rate = output_rate(cha.response.response_stages)
    ids = sorted(
        {
            f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}"
            for net in inventory
            for sta in net
            for cha in sta
        }
    )
    if seed_id is not None:
        for net in inventory:
            for sta in net:
                sta.channels = [
                    cha
                    for cha in sta
                    if f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}"
                    == seed_id
                ]
            net.stations = [sta for sta in net if sta.channels]
        inventory.networks = [net for net in inventory if net.stations]
        if not inventory.networks:
            raise LookupError(
                f"No channel {seed_id} in {path} (channels: "
                f"{', '.join(ids) or 'none'})."
            )

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
    inventory = read_channels(path, seed_id)
    channels = [
        (f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}", cha)
        for net in inventory
        for sta in net
        for cha in sta
    ]
    ids = ", ".join(sorted({code for code, _ in channels})) or "none"
    match channels:
        case [(_, channel)] if channel.response is not None:
            response = channel.response
        case [_]:
            raise ValueError(f"The channel {ids} of {path} has no response.")
        case []:
            raise LookupError(f"No channel in {path}.")
        case _:
            raise LookupError(
                f"{path} has {len(channels)} channels or epochs: pick one with "
                f"FILE#NET.STA.LOC.CHA (channels: {ids})."
            )

    return response


def split_channels(inventory: Inventory) -> list[tuple[str, Inventory]]:
    """Each channel of an inventory in an inventory of its own, with its SEED id

    Args:
        inventory: inventory of responses.

    Returns:
        the SEED id NET.STA.LOC.CHA and the inventory of each channel.


    """
    singles = list()
    for network in inventory:
        for station in network:
            for channel in station:
                # the inventory, with this network, station and channel only
                single = inventory.copy()
                single.networks = [network.copy()]
                single[0].stations = [station.copy()]
                single[0][0].channels = [channel.copy()]
                seedid = (
                    f"{network.code}.{station.code}."
                    f"{channel.location_code}.{channel.code}"
                )
                singles.append((seedid, single))

    return singles


def write_inventory(
    inventory: Inventory, path: Path, fileformat: ResponseFormat
) -> Path:
    """Write the responses of an inventory in a format

    StationXML and SACPZ by obspy, RESP by write_resp. SACPZ holds the channels
    with poles and zeros and an input in m, m/s or m/s**2 only: obspy would skip
    the others, so they are refused before writing. Its constant is A0 times the
    overall sensitivity (rdseed, IRIS and obspy), right only when A0 normalizes
    the poles and zeros at the frequency of the sensitivity: the first poles and
    zeros stage of a copy is normalized there before obspy writes it.

    Args:
        inventory: inventory of responses.
        path: file to write.
        fileformat: stationxml, resp or sacpz.

    Returns:
        the file written.

    Raises:
        ValueError: if a channel has no response, or SACPZ cannot hold it.
        OSError: if the file cannot be written.


    """
    channels = [
        (f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}", cha)
        for net in inventory
        for sta in net
        for cha in sta
    ]
    missing = [seedid for seedid, cha in channels if cha.response is None]
    if missing:
        raise ValueError(f"No response to write for {', '.join(missing)}.")
    match fileformat:
        case "stationxml":
            inventory.write(str(path), format="STATIONXML")
        case "resp":
            path.write_text(write_resp(inventory))
        case "sacpz":
            # the first poles and zeros stage of each channel, the one SACPZ keeps
            firsts = [
                next(
                    (
                        stage
                        for stage in cha.response.response_stages
                        if isinstance(stage, PolesZerosResponseStage)
                    ),
                    None,
                )
                for _, cha in channels
            ]
            refused = [
                seedid
                for (seedid, cha), first in zip(channels, firsts, strict=True)
                if cha.response.instrument_sensitivity is None
                or (cha.response.instrument_sensitivity.input_units or "").upper()
                not in SACPZ_UNITS
                or first is None
                or first.pz_transfer_function_type not in SACPZ_TRANSFER_TYPES
            ]
            if refused:
                raise ValueError(
                    "SACPZ holds only the channels with analog poles and zeros and an "
                    f"input in m, m/s or m/s**2: not {', '.join(refused)}."
                )
            # CONSTANT = A0 x sensitivity: A0 of a copy at the sensitivity frequency
            normalized = inventory.copy()
            for net in normalized:
                for sta in net:
                    for cha in sta:
                        response = cha.response
                        frequency = response.instrument_sensitivity.frequency
                        first = next(
                            stage
                            for stage in response.response_stages
                            if isinstance(stage, PolesZerosResponseStage)
                        )
                        if frequency:
                            first.normalization_frequency = frequency
                            first.normalization_factor = (
                                first.calculate_normalization_factor()
                            )

            # obspy warns that it keeps the first poles and zeros: verify_written
            # says it
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                normalized.write(str(path), format="SACPZ")

    return path


def verify_written(
    inventory: Inventory, path: Path, fileformat: ResponseFormat
) -> list[str]:
    """Read a written file back and compare each channel with the inventory

    StationXML and RESP are read back by obspy and must give the same curve
    (LOSSLESS_TOLERANCE) or the same polynomial; SACPZ, which keeps the first
    poles and zeros stage and the overall sensitivity, is read by read_sacpz and
    its difference with the whole response noted.

    Args:
        inventory: inventory written.
        path: file written with write_inventory.
        fileformat: stationxml, resp or sacpz.

    Returns:
        the notes on what SACPZ keeps, and on the channels without a curve to
        check.

    Raises:
        ValueError: if the file does not hold the channels written, or a lossless
            format reads back different.
        OSError: if the file cannot be read.


    """
    written = [
        (f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}", cha)
        for net in inventory
        for sta in net
        for cha in sta
    ]
    notes = list()
    match fileformat:
        case "sacpz":
            blocks = read_sacpz(path.read_text())
            if [seedid for seedid, *_ in blocks] != [seedid for seedid, _ in written]:
                raise ValueError(f"{path} does not hold the channels written.")
            for (seedid, cha), (_, zeros, poles, constant) in zip(
                written, blocks, strict=True
            ):
                response = cha.response
                frequencies = check_frequencies(cha.sample_rate)
                first = next(
                    stage
                    for stage in response.response_stages
                    if isinstance(stage, PolesZerosResponseStage)
                )

                # the whole response in displacement, as the zeros obspy added
                added = len(zeros) - len(first.zeros)
                whole = [
                    value * (2.0 * math.pi * frequency) ** added
                    for value, frequency in zip(
                        evalresp_curve(response, frequencies), frequencies, strict=True
                    )
                ]
                kept = [
                    pz_amplitude(zeros, poles, constant, frequency)
                    for frequency in frequencies
                ]
                inband = [
                    k
                    for k, frequency in enumerate(frequencies)
                    if frequency <= 0.25 * frequencies[-1]
                ]
                low = relative_difference(
                    [whole[k] for k in inband], [kept[k] for k in inband]
                )
                top = relative_difference(whole[-1:], kept[-1:])
                dropped = len(response.response_stages) - 1
                notes.append(
                    f"{seedid}: SACPZ keeps stage {first.stage_sequence_number} and "
                    f"the overall sensitivity, and drops the other {dropped} stages: "
                    f"within {low:.2%} up to {frequencies[inband[-1]]:.3g} Hz, "
                    f"{top:.2%} at {frequencies[-1]:.3g} Hz"
                )
        case _:
            back = read_inventory(str(path))
            read = [
                (f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}", cha)
                for net in back
                for sta in net
                for cha in sta
            ]
            if [seedid for seedid, _ in read] != [seedid for seedid, _ in written]:
                raise ValueError(f"{path} does not hold the channels written.")
            for (seedid, before), (_, after) in zip(written, read, strict=True):
                difference = response_difference(
                    before.response, after.response, before.sample_rate
                )
                if difference is None:
                    notes.append(f"{seedid}: no sensitivity, the curve is not checked")
                elif difference > LOSSLESS_TOLERANCE:
                    raise ValueError(
                        f"{path}: {seedid} reads back {difference:.1e} different "
                        "from what was written."
                    )

    return notes


def response_difference(
    before: Response, after: Response, sample_rate: float | None
) -> float | None:
    """Largest relative difference between the curves of two responses

    A polynomial compares its coefficients: obspy reads the polynomial of
    StationXML as the one of the channel, and the one of RESP as a stage 0.

    Args:
        before: response of reference.
        after: response compared.
        sample_rate: sample rate of the channel, for the frequencies of the check.

    Returns:
        the difference at the frequencies of check_frequencies (0 or inf for a
        polynomial), None when the reference has no sensitivity to compare with.


    """
    polynomial = before.instrument_polynomial
    difference: float | None = None
    if polynomial is not None:
        again = [
            list(stage.coefficients)
            for stage in after.response_stages
            if isinstance(stage, PolynomialResponseStage)
        ]
        channel_polynomial = after.instrument_polynomial
        if channel_polynomial is not None:
            again = [list(channel_polynomial.coefficients)]
        same = again == [list(polynomial.coefficients)]
        difference = 0.0 if same else math.inf
    elif before.instrument_sensitivity is not None:
        frequencies = check_frequencies(sample_rate)
        difference = relative_difference(
            evalresp_curve(before, frequencies), evalresp_curve(after, frequencies)
        )

    return difference


def stationxml_text(inventory: Inventory) -> str:
    """StationXML of an inventory, as text

    Args:
        inventory: inventory written.

    Returns:
        the StationXML document.


    """
    buffer = io.BytesIO()
    inventory.write(buffer, format="STATIONXML")
    text = buffer.getvalue().decode("utf-8")

    return text


def set_provenance(inventory: Inventory, text: str) -> Inventory:
    """Copy of an inventory with a comment on each channel saying what built it

    Args:
        inventory: inventory built.
        text: value of the comment (see core.assets.provenance_text), with the
            subject PROVENANCE_SUBJECT.

    Returns:
        the inventory with the comments; the given one is not changed.


    """
    marked = inventory.copy()
    for network in marked:
        for station in network:
            for channel in station:
                channel.comments.append(Comment(text, subject=PROVENANCE_SUBJECT))

    return marked


def evalresp_curve(response: Response, frequencies: list[float]) -> list[float]:
    """Amplitude of a response by obspy's evalresp, in its own units

    Args:
        response: response with a sensitivity.
        frequencies: frequencies in Hz.

    Returns:
        the amplitude at each frequency.


    """
    values = response.get_evalresp_response_for_frequencies(frequencies, output="DEF")
    curve = [float(abs(value)) for value in values]

    return curve


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
    station = Station(
        PLACEHOLDER_STATION, 0.0, 0.0, 0.0, [channel], start_date=PLACEHOLDER_START
    )
    network = Network(PLACEHOLDER_NETWORK, [station], start_date=PLACEHOLDER_START)
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
