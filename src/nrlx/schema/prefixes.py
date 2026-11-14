"""Structs of the instconfig parameter codes, as returned by the /prefix-lookup
endpoint


"""

from __future__ import annotations

import msgspec


class PrefixInput(msgspec.Struct, frozen=True):
    """A two-letter code of the parameters packed in the instconfigs

    For example LP120 is a long-period corner of 120 s, FR500 a final sample rate of
    500 Hz.

    Args:
        prefix: two-letter code, for example LP.
        description: meaning of the code, with underscores between the words.
        question: question that the parameter answers.


    """

    prefix: str
    description: str
    question: str = ""
