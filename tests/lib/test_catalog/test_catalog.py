from __future__ import annotations

import json

import pytest

from nrlx.io.cache import decode_catalog
from nrlx.models.catalog import Catalog


def test_decode_parses_the_tree(catalog):
    assert catalog.format_version == 1.0
    assert catalog.detail == "root detail"
    assert len(catalog.get_elements()) == 2
    assert len(catalog.get_manufacturers()) == 3
    assert len(catalog.get_models()) == 4
    assert len(catalog.get_configurations()) == 5


def test_filters_are_case_insensitive_substrings(catalog):
    manufacturers = catalog.get_manufacturers(element_name="sensor", name="strec")

    assert [manufacturer.name for _, manufacturer in manufacturers] == ["Streckeisen"]
    assert catalog.get_elements("SENSOR")[0].name == "sensor"
    assert [
        model.name
        for _, _, model in catalog.get_models("sensor", "streckeisen", name="sts")
    ] == ["STS-2", "STS-1"]


def test_configurations_carry_their_parents(catalog):
    rows = catalog.get_configurations("sensor")

    assert len(rows) == 4
    element, manufacturer, model, configuration = rows[0]
    assert element.name == "sensor"
    assert manufacturer.name == "Streckeisen"
    assert model.name == "STS-2"
    assert (
        configuration.instconfig
        == "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
    )
    assert configuration.version == "2020-01-01"
    assert configuration.description == "Streckeisen; STS-2; gain 1500"
    assert configuration.parameters == {"Sensitivity": "1500 V/m/s"}


def test_missing_optional_fields_get_defaults(catalog):
    [(_, manufacturer, model, configuration)] = [
        row for row in catalog.get_configurations() if row[2].name == "STS-1"
    ]

    assert manufacturer.detail == "streckeisen detail"
    assert model.detail == ""
    assert configuration.description == ""
    assert configuration.parameters == {}


# the sensors of the test catalog
STS2_1500 = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
STS2_750 = "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel"
STS1 = "sensor_Streckeisen_STS-1_LP360"
TRILLIUM = "sensor_Nanometrics_Trillium-120_SG1200"


def make_catalog(configurations: list[tuple[str, dict[str, str]]]) -> Catalog:
    """Catalog of one sensor model, Lunitek TELLUS, with these instconfigs and
    parameters"""
    content = {
        "NRLCatalog": {
            "formatversion": 1.0,
            "element": [
                {
                    "name": "sensor",
                    "manufacturer": [
                        {
                            "name": "Lunitek",
                            "model": [
                                {
                                    "name": "TELLUS",
                                    "configuration": [
                                        {
                                            "instconfig": instconfig,
                                            "version": "2024-01-01",
                                            "parameters": parameters,
                                        }
                                        for instconfig, parameters in configurations
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    }

    return decode_catalog(json.dumps(content).encode())


def instconfigs(rows) -> list[str]:
    return [configuration.instconfig for *_, configuration in rows]


@pytest.mark.parametrize(
    ("keys", "found"),
    [
        # a word: a manufacturer, a model, a part of the instconfig, a value
        (["Streckeisen"], [STS2_1500, STS2_750, STS1]),
        (["STS-2"], [STS2_1500, STS2_750]),
        (["SG750"], [STS2_750]),
        (["1500 V/m/s"], [STS2_1500]),
        # every key, in any order
        (["SG750", "streckeisen"], [STS2_750]),
        (["streckeisen", "SG750"], [STS2_750]),
        # a condition by its code, the numbers compared as numbers
        (["SG=1500"], [STS2_1500]),
        (["SG=150"], []),
        # a condition by the start of a word of the parameter name, and ranges
        (["sens>=1000"], [STS2_1500]),
        (["SG=..1000"], [STS2_750]),
        (["SG=500..2000"], [STS2_1500, STS2_750]),
        # nothing
        (["nonexistent"], []),
    ],
)
def test_find(catalog, prefixes, keys, found):
    assert instconfigs(catalog.find(keys, prefixes, "sensor").rows) == found


def test_find_respects_the_element(catalog, prefixes):
    assert catalog.find(["Streckeisen"], prefixes, "datalogger").rows == []
    assert instconfigs(catalog.find(["FV=40"], prefixes).rows) == [
        "datalogger_Quanterra_Q330_FV40Vpp_FR100"
    ]


def test_find_keeps_the_lowest_total_tier(prefixes):
    catalog = make_catalog(
        [
            ("sensor_Lunitek_TELLUS_LP1_SG400", {"Long-Period_Corner": "1 s"}),
            ("sensor_Lunitek_TELLUS_LP10_SG400", {"Long-Period_Corner": "10 s"}),
            ("sensor_Lunitek_TELLUS_LP120_SG1500", {"Long-Period_Corner": "120 s"}),
        ]
    )

    # LP1 is whole in one, the start of a part in the others
    found = catalog.find(["tellus", "LP1"], prefixes)
    loose = catalog.find(["luni", "LP12"], prefixes)

    assert instconfigs(found.rows) == ["sensor_Lunitek_TELLUS_LP1_SG400"]
    assert found.notes == []
    assert instconfigs(loose.rows) == ["sensor_Lunitek_TELLUS_LP120_SG1500"]
    assert loose.notes == ["luni: start of Lunitek", "LP12: start of LP120"]


def test_find_notes_a_word_inside_a_text(catalog, prefixes):
    found = catalog.find(["groundvel"], prefixes, "sensor")

    assert instconfigs(found.rows) == [STS2_1500, STS2_750]
    assert found.notes == ["groundvel: found inside a text only"]


def test_find_lists_the_parameters_that_vary(catalog, prefixes):
    found = catalog.find(["STS-2"], prefixes, "sensor")
    single = catalog.find(["SG750"], prefixes, "sensor")

    assert found.varying == {"Sensitivity": ["750 V/m/s", "1500 V/m/s"]}
    assert single.varying == {}


def test_find_ambiguous_parameter_name_needs_the_other_keys(prefixes):
    catalog = make_catalog(
        [
            ("sensor_Lunitek_TELLUS_LP1", {"Long-Period_Corner": "1 s"}),
            ("sensor_Lunitek_TELLUS_HF50", {"High-Frequency_Corner": "50 Hz"}),
        ]
    )

    # corner stands for both parameters, LP1 leaves one
    with pytest.raises(ValueError, match="stands for several parameters"):
        catalog.find(["corner=1"], prefixes)
    assert instconfigs(catalog.find(["LP1", "corner=1"], prefixes).rows) == [
        "sensor_Lunitek_TELLUS_LP1"
    ]


def test_find_number_leaves_out_the_parameters_without_numbers(prefixes):
    catalog = make_catalog(
        [
            (
                "sensor_Lunitek_TELLUS_SG400",
                {"Sensitivity": "400 V/m/s", "Sensor_Type": "groundVel"},
            ),
            (
                "sensor_Lunitek_TELLUS_SG2000",
                {"Sensitivity": "2000 V/m/s", "Sensor_Type": "groundVel"},
            ),
        ]
    )

    # sens is Sensitivity or Sensor_Type; only Sensitivity has numbers
    assert instconfigs(catalog.find(["sens>1000"], prefixes).rows) == [
        "sensor_Lunitek_TELLUS_SG2000"
    ]
    with pytest.raises(ValueError, match="stands for several parameters"):
        catalog.find(["sens=groundVel"], prefixes)


@pytest.mark.parametrize(
    ("keys", "hints"),
    [
        (["streckeisn"], ["streckeisn: no match. Did you mean Streckeisen?"]),
        (
            ["STS-1", "SG1500"],
            [
                "STS-1: no match with the other keys.",
                "SG1500: no match with the other keys.",
            ],
        ),
        (
            ["STS-2", "SG=999"],
            [
                "SG=999: no match with the other keys. "
                "Values there: 750 V/m/s, 1500 V/m/s"
            ],
        ),
        (
            ["STS-1", "SG=1"],
            ["SG=1: no parameter 'SG' with the other keys. Parameters there: none"],
        ),
    ],
)
def test_find_hints_when_nothing_matches(catalog, prefixes, keys, hints):
    found = catalog.find(keys, prefixes, "sensor")

    assert found.rows == []
    assert found.hints == hints


def test_find_hints_keys_that_only_fail_together(prefixes):
    # every pair of the four keys matches, no three of them
    pairs = ["AA_BB", "AA_CC", "AA_DD", "BB_CC", "BB_DD", "CC_DD"]
    catalog = make_catalog([(f"sensor_Lunitek_TELLUS_{pair}", {}) for pair in pairs])

    found = catalog.find(["AA", "BB", "CC", "DD"], prefixes)

    assert found.rows == []
    assert found.hints == ["No configuration matches all the keys together."]


def test_resolve_returns_the_single_match(catalog, prefixes):
    configuration = catalog.resolve("sensor", ["streckeisen", "SG=1500"], prefixes)

    assert configuration.instconfig == STS2_1500


def test_resolve_raises_not_found_with_the_hints(catalog, prefixes):
    with pytest.raises(LookupError) as excinfo:
        catalog.resolve("sensor", ["streckeisn"], prefixes)

    message = str(excinfo.value)
    assert "No sensor configuration matches." in message
    assert "  streckeisn: no match. Did you mean Streckeisen?" in message


def test_resolve_raises_ambiguous_with_what_varies_and_the_candidates(
    catalog, prefixes
):
    with pytest.raises(LookupError) as excinfo:
        catalog.resolve("sensor", ["STS-2"], prefixes)

    message = str(excinfo.value)
    assert "Ambiguous sensor selection: 2 configurations match" in message
    assert "  Sensitivity: 750 V/m/s, 1500 V/m/s" in message
    assert f"  {STS2_1500}" in message
    assert f"  {STS2_750}" in message
    assert "more" not in message
