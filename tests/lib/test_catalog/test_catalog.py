from __future__ import annotations

import pytest


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
    rows = catalog.get_configurations("sensor", "Streckeisen", "STS-2")

    assert len(rows) == 2
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
    [(_, manufacturer, model, configuration)] = catalog.get_configurations(
        model_name="STS-1"
    )

    assert manufacturer.detail == "streckeisen detail"
    assert model.detail == ""
    assert configuration.description == ""
    assert configuration.parameters == {}


@pytest.mark.parametrize(
    "key, instconfigs",
    [
        # manufacturer name
        (
            "Streckeisen",
            [
                "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel",
                "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel",
                "sensor_Streckeisen_STS-1_LP360",
            ],
        ),
        # model name
        ("Trillium", ["sensor_Nanometrics_Trillium-120_SG1200"]),
        # instconfig
        ("FV40Vpp", ["datalogger_Quanterra_Q330_FV40Vpp_FR100"]),
        # parameter value
        ("1500 V", ["sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"]),
        # parameter name
        (
            "sensitivity",
            [
                "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel",
                "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel",
            ],
        ),
        # description
        ("gain 750", ["sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel"]),
        # nothing
        ("nonexistent", []),
    ],
)
def test_a_key_searches_every_field(catalog, key, instconfigs):
    rows = catalog.get_configurations(keys=[key])

    assert [configuration.instconfig for _, _, _, configuration in rows] == instconfigs


def test_all_the_keys_must_match(catalog):
    rows = catalog.get_configurations(keys=["streckeisen", "STS-2", "750"])

    assert [configuration.instconfig for _, _, _, configuration in rows] == [
        "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel"
    ]


def test_keys_respect_the_element(catalog):
    assert catalog.get_configurations("datalogger", keys=["Streckeisen"]) == []


def test_resolve_returns_the_single_match(catalog):
    configuration = catalog.resolve(
        "sensor", manufacturer_name="Streckeisen", model_name="STS-1"
    )

    assert configuration.instconfig == "sensor_Streckeisen_STS-1_LP360"


def test_resolve_with_keys_narrows_to_unique(catalog):
    # STS-2 alone is ambiguous (two gains), a parameter value settles it
    configuration = catalog.resolve("sensor", keys=["streckeisen", "STS-2", "1500"])

    assert (
        configuration.instconfig
        == "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
    )


def test_resolve_with_keys_matches_parameter_values(catalog):
    configuration = catalog.resolve("datalogger", keys=["40Vpp"])

    assert configuration.instconfig == "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def test_resolve_raises_not_found(catalog):
    with pytest.raises(LookupError, match="No sensor configuration found"):
        catalog.resolve("sensor", manufacturer_name="Nonexistent")


def test_resolve_raises_not_found_with_keys(catalog):
    with pytest.raises(LookupError, match="No sensor configuration found"):
        catalog.resolve("sensor", keys=["STS-2", "does-not-exist"])


def test_resolve_raises_ambiguous_listing_the_candidates(catalog):
    with pytest.raises(LookupError) as excinfo:
        catalog.resolve("sensor", keys=["STS-2"])

    message = str(excinfo.value)
    assert "Ambiguous sensor selection: 2 configurations match" in message
    assert "  sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel" in message
    assert "  sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel" in message
    assert "more" not in message
