"""Assets: the provenance comment of a built channel, the UIDs, and the keys on
the columns of an asset


"""

from __future__ import annotations

import re

from nrlx.core.matching import compare, split_condition
from nrlx.schema.response import Source

# subject of the StationXML comment saying what a channel is built from
PROVENANCE_SUBJECT = "nrlx"

# the part of a provenance given as a response (a file) instead of NRL keys
GIVEN_PART = "file"

# a UID names a folder of an export: letters, digits, dot, dash and underscore
UID = re.compile(r"^[A-Za-z0-9_-][A-Za-z0-9._-]*$")

# the keys on the columns of an asset instead of its NRL parts
RATE_KEY = "rate"
UNITS_KEY = "units"


def provenance_text(version: str, source: Source, parts: list[tuple[str, str]]) -> str:
    """Text of the provenance comment of a channel built by nrlx

    Args:
        version: version of nrlx.
        source: where the NRL parts come from, service or local.
        parts: element and instconfig of each part, in the order of the signal;
            GIVEN_PART for a part given as a response.

    Returns:
        for example "built by nrlx 0.3.0 (service): sensor=sensor_A
        datalogger=file".


    """
    built = " ".join(f"{element}={instconfig}" for element, instconfig in parts)
    text = f"built by nrlx {version} ({source}): {built}"

    return text


def read_source(text: str) -> Source | None:
    """Source of the NRL parts of a provenance comment written by provenance_text

    Args:
        text: value of the comment.

    Returns:
        service or local; None if the text is not a provenance, or was written
        before the source was recorded.


    """
    head, colon, _ = text.partition(": ")
    source: Source | None = None
    if colon and head.startswith("built by nrlx "):
        match head.split()[-1]:
            case "(service)":
                source = "service"
            case "(local)":
                source = "local"

    return source


def read_provenance(text: str) -> list[tuple[str, str]]:
    """Parts of a provenance comment written by provenance_text

    Args:
        text: value of the comment.

    Returns:
        element and instconfig of each part, empty if the text is not a
        provenance.


    """
    _, colon, built = text.partition(": ")
    words = [word.partition("=") for word in built.split()]
    parts = [
        (element, instconfig)
        for element, equal, instconfig in words
        if equal and element and instconfig
    ]
    found = parts if colon and text.startswith("built by nrlx ") else []

    return found


def check_uid(uid: str) -> str:
    """A UID of an asset, as it can name a folder of an export

    Args:
        uid: UID given, or the station code.

    Returns:
        the UID.

    Raises:
        ValueError: if it has other characters than letters, digits, dot, dash and
            underscore, or starts with a dot.


    """
    if not UID.match(uid):
        raise ValueError(
            f"The UID {uid!r} must be letters, digits, '.', '-' or '_', not "
            "starting with '.'."
        )

    return uid


def split_asset_keys(keys: list[str]) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Keys of an asset: those of its NRL parts, and the conditions on its columns

    Args:
        keys: keys as in nrlx response (STS-2, FR=100), plus rate=100 and units=m/s
            on the sample rate and the input units of the asset.

    Returns:
        the keys of the NRL parts, and the name, operator and value of each
        condition on the rate or the units.

    Raises:
        ValueError: if a range has no bound.


    """
    parts: list[str] = list()
    columns: list[tuple[str, str, str]] = list()
    for key in keys:
        conditions = split_condition(key)
        if conditions and all(
            name.lower() in (RATE_KEY, UNITS_KEY) for name, _, _ in conditions
        ):
            columns += [
                (name.lower(), operator, value) for name, operator, value in conditions
            ]
        else:
            parts.append(key)

    return parts, columns


def column_holds(
    rate: float | None, units: str, condition: tuple[str, str, str]
) -> bool:
    """Whether the rate or the units of an asset satisfy a condition

    Args:
        rate: sample rate of the asset, None without digital stages.
        units: input units of the asset.
        condition: name (rate or units), operator and value.

    Returns:
        whether the condition holds; a condition on the rate fails without one.


    """
    name, operator, value = condition
    match name:
        case "rate":
            holds = rate is not None and compare(f"{rate:g}", operator, value)
        case _:
            holds = compare(units, operator, value)

    return holds
