"""Text matching of the catalog filters and of the keys

A key is a word (lunitek, LP1, Q330HR_PG1) or a condition on a parameter (FR=40,
corner>=60, FR=100..500). A word is found at its best tier: a whole part of the
instconfig or a whole name, else the start of one, else anywhere in the texts.


"""

from __future__ import annotations

import re

# tiers of a word found in a configuration, from the best; 0 is not found
WHOLE = 1
START = 2
ANYWHERE = 3
NOT_FOUND = 0

# a condition: a parameter name, an operator and a value, for example FR>=100
CONDITION = re.compile(
    r"^(?P<name>[A-Za-z][\w-]*)(?P<operator><=|>=|=|<|>)(?P<value>.+)$"
)

# the number at the start of a value, for example 40 in "40 Hz" or 2 in "2Vpp"
NUMBER = re.compile(r"^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")


def split_condition(key: str) -> list[tuple[str, str, str]]:
    """Conditions of a key, empty for a word

    The range FR=100..500 is two conditions, FR>=100 and FR<=500; FR=100.. and
    FR=..500 keep one bound.

    Args:
        key: key typed by the user.

    Returns:
        name, operator and value of each condition.

    Raises:
        ValueError: if a range has no bound, for example FR=.. .


    """
    conditions: list[tuple[str, str, str]] = list()
    match CONDITION.match(key):
        case None:
            pass
        case found if found["operator"] == "=" and ".." in found["value"]:
            low, high = found["value"].split("..", 1)
            if not low and not high:
                raise ValueError(f"The range of {key!r} needs a bound")
            if low:
                conditions.append((found["name"], ">=", low))
            if high:
                conditions.append((found["name"], "<=", high))
        case found:
            conditions.append((found["name"], found["operator"], found["value"]))

    return conditions


def to_number(text: str) -> float | None:
    """Number at the start of a text, None without one

    Args:
        text: value, for example "40 Hz", "2Vpp" or "Linear".

    Returns:
        the number, None when the text does not start with one.


    """
    found = NUMBER.match(text.strip())
    number = float(found.group()) if found else None

    return number


def compare(value: str, operator: str, wanted: str) -> bool:
    """Whether a parameter value satisfies a condition

    Two numbers are compared as numbers (FR=40 is "40 Hz", not "400 Hz"); otherwise
    the texts are equal, case-insensitive, and the order operators are false.

    Args:
        value: value of the parameter in the configuration, for example "40 Hz".
        operator: operator of the condition: =, <, >, <= or >=.
        wanted: value of the condition, for example "40".

    Returns:
        whether the condition holds.

    Raises:
        ValueError: if the operator is not one of the five.


    """
    number, wantednumber = to_number(value), to_number(wanted)
    if number is not None and wantednumber is not None:
        match operator:
            case "=":
                holds = number == wantednumber
            case "<":
                holds = number < wantednumber
            case ">":
                holds = number > wantednumber
            case "<=":
                holds = number <= wantednumber
            case ">=":
                holds = number >= wantednumber
            case _:
                raise ValueError(f"Unknown operator {operator!r}")
    else:
        holds = operator == "=" and value.strip().lower() == wanted.strip().lower()

    return holds


def word_tier(word: str, instconfig: str, names: list[str], texts: list[str]) -> int:
    """Best tier at which a word is found in a configuration

    Args:
        word: key without an operator, for example LP1 or Q330HR_PG1.
        instconfig: instconfig of the configuration, its parts split by "_".
        names: whole names of the configuration: manufacturer, model and the
            parameter values.
        texts: every text searched anywhere: the names, the instconfig, the
            description and the parameter names.

    Returns:
        WHOLE, START, ANYWHERE, or NOT_FOUND.


    """
    lowered = word.lower()
    parts = instconfig.lower().split("_")
    lowerednames = [name.lower() for name in names]

    # a run of whole parts, wrapped in underscores, or a whole name
    if f"_{lowered}_" in f"_{instconfig.lower()}_" or lowered in lowerednames:
        tier = WHOLE
    elif any(text.startswith(lowered) for text in parts + lowerednames):
        tier = START
    elif any(lowered in text.lower() for text in texts):
        tier = ANYWHERE
    else:
        tier = NOT_FOUND

    return tier


def contains(text: str, query: str | None) -> bool:
    """Whether the text contains the query, case-insensitive

    A query None is contained in every text, as a filter not specified.

    Args:
        text: text to search, for example a manufacturer name.
        query: text to find, None for any text.

    Returns:
        whether the query is in the text.


    """
    contained = query is None or query.lower() in text.lower()

    return contained


def contains_keys(texts: list[str], keys: list[str]) -> bool:
    """Whether each of the keys is contained in at least one of the texts

    The keys are unordered and case-insensitive, as the key lists of the ObsPy NRL
    v1 client: every key must match, each in any of the texts. No keys match any
    texts.

    Args:
        texts: texts to search, for example the names and parameters of a
            configuration.
        keys: texts to find.

    Returns:
        whether all the keys are found.


    """
    contained = all(any(contains(text, key) for text in texts) for key in keys)

    return contained
