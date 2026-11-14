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


def resolve_parameter(
    name: str,
    wanted: str,
    codes: list[tuple[str, str]],
    values: dict[str, list[str]],
) -> list[str]:
    """Parameter names that the name of a condition stands for

    A code of the table (FR) stands for its parameter (Final_Sample_Rate) only, none
    when the configurations searched do not have it; any other name is a whole
    parameter name or the start of one of its words (corner for
    Long-Period_Corner), case-insensitive. A number leaves out the parameters
    without a number in their values: sens>1000 is Sensitivity, not Sensor_Type.

    Args:
        name: name of the condition, for example FR or corner.
        wanted: value of the condition, for example 40.
        codes: code and parameter name of each code of the table.
        values: values of each parameter in the configurations searched, by name.

    Returns:
        the parameter names, sorted: several when the name is ambiguous, none when
        it is unknown.


    """
    lowered = name.lower()

    # a code stands for its parameter, among the parameters searched
    iscode = any(code.lower() == lowered for code, _ in codes)
    bycode = [
        parameter
        for code, parameter in codes
        if code.lower() == lowered and parameter in values
    ]

    # a whole name, or the start of a word of the name
    byname = [
        parameter
        for parameter in values
        if parameter.lower() == lowered
        or any(
            word.startswith(lowered)
            for word in parameter.lower().replace("-", "_").split("_")
        )
    ]

    # a number, among the names with numbers when there are some
    numeric = [
        parameter
        for parameter in byname
        if any(to_number(value) is not None for value in values[parameter])
    ]
    if to_number(wanted) is not None and numeric:
        byname = numeric
    parameters = sorted(set(bycode if iscode else byname))

    return parameters


def sort_values(values: list[str]) -> list[str]:
    """Distinct values of a parameter: the numbers by value, then the texts

    Args:
        values: values of a parameter, for example "100 Hz", "40 Hz", "40 Hz".

    Returns:
        the distinct values, sorted, for example "40 Hz", "100 Hz".


    """
    distinct = sorted(set(values))
    numbers = sorted(
        [
            (number, value)
            for value in distinct
            if (number := to_number(value)) is not None
        ]
    )
    texts = [value for value in distinct if to_number(value) is None]
    sortedvalues = [value for _, value in numbers] + texts

    return sortedvalues


def varying_values(parameters: list[dict[str, str]]) -> dict[str, list[str]]:
    """Values of each parameter that differs between configurations

    Args:
        parameters: parameters of each configuration, values by name.

    Returns:
        the sorted values of each parameter with more than one value, by name in
        alphabetical order.


    """
    names = sorted({name for values in parameters for name in values})
    found = {
        name: sort_values([values[name] for values in parameters if name in values])
        for name in names
    }
    varying = {name: values for name, values in found.items() if len(values) > 1}

    return varying
