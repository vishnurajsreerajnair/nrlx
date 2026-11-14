from __future__ import annotations

import pytest

from nrlx.models.instrument import Instrument


@pytest.mark.parametrize(
    "manufacturer, model, keys",
    [("Streckeisen", None, []), (None, "STS-2", []), (None, None, ["STS-2"])],
)
def test_instconfig_and_filters_are_rejected(manufacturer, model, keys):
    with pytest.raises(ValueError, match="not both"):
        Instrument(
            instconfig="sensor_A", manufacturer=manufacturer, model=model, keys=keys
        )


def test_exact_instconfig_skips_the_catalog(catalog):
    instrument = Instrument(instconfig="sensor_not_in_the_catalog")

    assert instrument.get_instconfig(catalog, "sensor") == "sensor_not_in_the_catalog"


def test_filters_resolve_in_the_catalog(catalog):
    instrument = Instrument(manufacturer="streck", model="STS-1")

    assert instrument.get_instconfig(catalog, "sensor") == (
        "sensor_Streckeisen_STS-1_LP360"
    )


def test_filters_respect_the_element(catalog):
    instrument = Instrument(keys=["Quanterra"])

    with pytest.raises(LookupError, match="No sensor configuration found"):
        instrument.get_instconfig(catalog, "sensor")
