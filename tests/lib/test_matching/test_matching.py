from __future__ import annotations

import pytest

from nrlx.core.matching import (
    ANYWHERE,
    NOT_FOUND,
    START,
    WHOLE,
    compare,
    split_condition,
    to_number,
    word_tier,
)

TELLUS = "sensor_Lunitek_TELLUS_LP10_SG400_STgroundVel"
Q330 = "datalogger_Quanterra_Q330HR_PG1_FR40_ADHR_LRbelow100_DENone"


@pytest.mark.parametrize(
    ("key", "conditions"),
    [
        ("lunitek", []),
        ("Q330HR_PG1", []),
        ("FR=40", [("FR", "=", "40")]),
        ("FV=40Vpp", [("FV", "=", "40Vpp")]),
        ("corner>=60", [("corner", ">=", "60")]),
        ("FR<200", [("FR", "<", "200")]),
        ("Long-Period_Corner>1", [("Long-Period_Corner", ">", "1")]),
        ("FR=100..500", [("FR", ">=", "100"), ("FR", "<=", "500")]),
        ("FR=100..", [("FR", ">=", "100")]),
        ("FR=..200", [("FR", "<=", "200")]),
    ],
)
def test_split_condition(key: str, conditions: list[tuple[str, str, str]]) -> None:
    assert split_condition(key) == conditions


def test_split_condition_refuses_a_range_without_bounds() -> None:
    with pytest.raises(ValueError, match="needs a bound"):
        split_condition("FR=..")


@pytest.mark.parametrize(
    ("text", "number"),
    [
        ("40 Hz", 40.0),
        ("2Vpp", 2.0),
        ("0.001", 0.001),
        ("-3 dB", -3.0),
        ("1e3", 1000.0),
        ("Linear", None),
        ("", None),
    ],
)
def test_to_number(text: str, number: float | None) -> None:
    assert to_number(text) == number


@pytest.mark.parametrize(
    ("value", "operator", "wanted", "holds"),
    [
        ("40 Hz", "=", "40", True),
        ("400 Hz", "=", "40", False),
        ("1 s", "=", "1", True),
        ("10 s", "=", "1", False),
        ("120 s", ">=", "60", True),
        ("30 s", ">=", "60", False),
        ("100 Hz", "<", "200", True),
        ("200 Hz", "<", "200", False),
        ("200 Hz", "<=", "200", True),
        ("200 Hz", ">", "100", True),
        ("Linear", "=", "linear", True),
        ("Linear", "=", "minimum", False),
        ("Linear", ">=", "linear", False),
    ],
)
def test_compare(value: str, operator: str, wanted: str, holds: bool) -> None:
    assert compare(value, operator, wanted) is holds


def test_compare_refuses_an_unknown_operator() -> None:
    with pytest.raises(ValueError, match="Unknown operator"):
        compare("40 Hz", "!=", "40")


@pytest.mark.parametrize(
    ("word", "instconfig", "names", "tier"),
    [
        # a whole part, a run of parts, the whole instconfig, a whole name
        ("LP10", TELLUS, ["Lunitek", "TELLUS"], WHOLE),
        ("lunitek", TELLUS, ["Lunitek", "TELLUS"], WHOLE),
        ("Q330HR_PG1", Q330, ["Quanterra", "Q330HR"], WHOLE),
        (Q330, Q330, ["Quanterra", "Q330HR"], WHOLE),
        ("400 V/m/s", TELLUS, ["Lunitek", "TELLUS", "400 V/m/s"], WHOLE),
        # the start of a part or of a name
        ("LP1", TELLUS, ["Lunitek", "TELLUS"], START),
        ("luni", TELLUS, ["Lunitek", "TELLUS"], START),
        # inside a text only
        ("groundvel", TELLUS, ["Lunitek", "TELLUS"], ANYWHERE),
        ("nitek", TELLUS, ["Lunitek", "TELLUS"], ANYWHERE),
        ("trillium", TELLUS, ["Lunitek", "TELLUS"], NOT_FOUND),
    ],
)
def test_word_tier(word: str, instconfig: str, names: list[str], tier: int) -> None:
    texts = [*names, instconfig]

    assert word_tier(word, instconfig, names, texts) == tier
