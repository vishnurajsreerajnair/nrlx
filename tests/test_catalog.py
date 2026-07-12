from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from nrlx.catalog import Catalog
from nrlx.exceptions import NrlxCacheError


def _configuration(
    instconfig: str,
    version: str,
    description: str = "",
    parameters: dict[str, str] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"instconfig": instconfig, "version": version}
    if description:
        data["description"] = description
    if parameters:
        data["parameters"] = parameters
    return data


def _model(
    name: str, configurations: list[dict[str, Any]], detail: str = ""
) -> dict[str, Any]:
    return {"name": name, "detail": detail, "configuration": configurations}


def _manufacturer(
    name: str, models: list[dict[str, Any]], detail: str = ""
) -> dict[str, Any]:
    return {"name": name, "detail": detail, "model": models}


def _element(
    name: str, manufacturers: list[dict[str, Any]], detail: str = ""
) -> dict[str, Any]:
    return {"name": name, "detail": detail, "manufacturer": manufacturers}


def _fixture_data() -> dict[str, Any]:
    sts2_configs = [
        _configuration(
            "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel",
            "2020-01-01",
            "Streckeisen; STS-2; gain 1500",
            {"Sensitivity": "1500"},
        ),
        _configuration(
            "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel",
            "2020-01-01",
            "Streckeisen; STS-2; gain 750",
            {"Sensitivity": "750"},
        ),
    ]
    trillium_configs = [
        _configuration("sensor_Nanometrics_Trillium-120_SG1200", "2019-01-01"),
    ]
    q330_configs = [
        _configuration("datalogger_Quanterra_Q330_FV40Vpp_FR100", "2018-01-01"),
    ]

    sensor_element = _element(
        "sensor",
        [
            _manufacturer(
                "Streckeisen",
                [_model("STS-2", sts2_configs)],
                detail="streckeisen detail",
            ),
            _manufacturer("Nanometrics", [_model("Trillium 120", trillium_configs)]),
        ],
        detail="sensor detail",
    )
    datalogger_element = _element(
        "datalogger",
        [_manufacturer("Quanterra", [_model("Q330", q330_configs)])],
    )

    return {
        "NRLCatalog": {
            "formatversion": 1.0,
            "detail": "root detail",
            "element": [sensor_element, datalogger_element],
        }
    }


def _write_catalog(tmp_path: Path, data: dict[str, Any]) -> Path:
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text(json.dumps(data), encoding="utf-8")
    return catalog_file


def test_from_file_parses_tree_once(tmp_path):
    catalog_file = _write_catalog(tmp_path, _fixture_data())
    catalog = Catalog.from_file(catalog_file)

    assert catalog.format_version == "1.0"
    assert catalog.element_count == 2
    assert catalog.manufacturer_count == 3
    assert catalog.model_count == 3
    assert catalog.configuration_count == 4

    summary = catalog.summary
    assert summary.path == catalog_file
    assert summary.element_count == 2
    assert summary.manufacturer_count == 3
    assert summary.model_count == 3
    assert summary.configuration_count == 4


def test_catalog_filtering_is_case_insensitive_substring(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    matches = catalog.manufacturers(element="sensor", name="strec")
    assert [m.name for m in matches] == ["Streckeisen"]

    assert catalog.elements(name="SENSOR")[0].name == "sensor"
    assert catalog.models(
        element="sensor", manufacturer="streckeisen", name="sts"
    )[0].name == "STS-2"


def test_configurations_round_trip_fields(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    configs = catalog.configurations(
        element="sensor", manufacturer="Streckeisen", model="STS-2"
    )
    assert len(configs) == 2

    first = configs[0]
    assert first.element == "sensor"
    assert first.manufacturer == "Streckeisen"
    assert first.model == "STS-2"
    assert first.instconfig == "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
    assert first.version == "2020-01-01"
    assert first.description == "Streckeisen; STS-2; gain 1500"
    assert first.parameters == {"Sensitivity": "1500"}


def test_search_matches_manufacturer_name(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("Streckeisen")

    assert len(results) == 2
    assert all(c.manufacturer == "Streckeisen" for c in results)


def test_search_matches_model_name(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("Trillium")

    assert len(results) == 1
    assert results[0].model == "Trillium 120"


def test_search_matches_instconfig_substring(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("FV40Vpp")

    assert len(results) == 1
    assert results[0].instconfig == "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def test_search_matches_parameter_value(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("1500")

    assert len(results) == 1
    assert results[0].parameters == {"Sensitivity": "1500"}


def test_search_matches_parameter_name(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("Sensitivity")

    # Both STS-2 configs carry a Sensitivity parameter.
    assert {c.instconfig for c in results} == {
        "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel",
        "sensor_Streckeisen_STS-2_EG3_SG750_LP120_STgroundVel",
    }


def test_search_matches_description(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("gain 750")

    assert len(results) == 1
    assert results[0].parameters == {"Sensitivity": "750"}


def test_configuration_matches_parameter_name_and_value(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))
    config = catalog.configurations(model="STS-2")[0]

    assert config.matches("Sensitivity")  # parameter name
    assert config.matches("1500")  # parameter value
    assert not config.matches("nonexistent")


def test_configuration_exact_lookup(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    found = catalog.configuration(
        "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
    )
    assert found is not None
    assert found.parameters == {"Sensitivity": "1500"}

    # A substring is not an exact match.
    assert catalog.configuration("STS-2") is None


def test_search_respects_element_scope(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    results = catalog.search("Streckeisen", element="datalogger")

    assert results == ()


def test_search_no_match_returns_empty(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    assert catalog.search("nonexistent") == ()


def test_scoped_query_methods(tmp_path):
    catalog = Catalog.from_file(_write_catalog(tmp_path, _fixture_data()))

    sensor = catalog.elements(name="sensor")[0]
    streckeisen = sensor.manufacturers(name="Streckeisen")[0]
    sts2 = streckeisen.models(name="STS-2")[0]
    configs = sts2.configurations()

    assert sensor.manufacturer_count == 2
    assert streckeisen.model_count == 1
    assert len(configs) == 2
    assert sts2.configuration_count == 2


def test_from_file_missing_file_raises(tmp_path):
    with pytest.raises(NrlxCacheError, match="Catalog file not found"):
        Catalog.from_file(tmp_path / "missing.json")


def test_from_file_invalid_json_raises(tmp_path):
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(NrlxCacheError, match="Invalid catalog JSON"):
        Catalog.from_file(catalog_file)


def test_from_file_missing_root_raises(tmp_path):
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text(json.dumps({"nope": {}}), encoding="utf-8")

    with pytest.raises(NrlxCacheError, match="missing NRLCatalog root"):
        Catalog.from_file(catalog_file)
