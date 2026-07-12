from __future__ import annotations

import json
from pathlib import Path

import pytest

from nrlx.catalog import Catalog, Configuration, Element, Manufacturer, Model
from nrlx.client import NRLClient
from nrlx.exceptions import NrlxResponseError
from nrlx.formats import ResponseFormat
from nrlx.nrl import BuiltResponse, Nrlx


def _configuration(
    element: str,
    manufacturer: str,
    model: str,
    instconfig: str,
    parameters: dict[str, str] | None = None,
) -> Configuration:
    return Configuration(
        element=element,
        manufacturer=manufacturer,
        model=model,
        instconfig=instconfig,
        version="1",
        parameters=parameters or {},
    )


def _fixture_catalog(tmp_path: Path) -> Catalog:
    sts2 = Model(
        element="sensor",
        manufacturer="Streckeisen",
        name="STS-2",
        _configurations=(
            _configuration(
                "sensor",
                "Streckeisen",
                "STS-2",
                "sensor_Streckeisen_STS-2_LP120_SG1500",
                parameters={"Sensitivity": "1500 V/m/s"},
            ),
            _configuration(
                "sensor",
                "Streckeisen",
                "STS-2",
                "sensor_Streckeisen_STS-2_LP120_SG750",
                parameters={"Sensitivity": "750 V/m/s"},
            ),
        ),
    )
    sts1 = Model(
        element="sensor",
        manufacturer="Streckeisen",
        name="STS-1",
        _configurations=(
            _configuration(
                "sensor", "Streckeisen", "STS-1", "sensor_Streckeisen_STS-1_LP360"
            ),
        ),
    )
    streckeisen = Manufacturer(
        element="sensor", name="Streckeisen", _models=(sts2, sts1)
    )
    sensor = Element(name="sensor", _manufacturers=(streckeisen,))

    q330 = Model(
        element="datalogger",
        manufacturer="Quanterra",
        name="Q330",
        _configurations=(
            _configuration(
                "datalogger",
                "Quanterra",
                "Q330",
                "datalogger_Quanterra_Q330_FV40Vpp_FR100",
                parameters={"Full-Scale_Voltage": "40Vpp"},
            ),
        ),
    )
    quanterra = Manufacturer(element="datalogger", name="Quanterra", _models=(q330,))
    datalogger = Element(name="datalogger", _manufacturers=(quanterra,))

    return Catalog(
        path=tmp_path / "catalog.json",
        format_version="1.0",
        _elements=(sensor, datalogger),
    )


def _nrlx(tmp_path: Path) -> Nrlx:
    return Nrlx(client=NRLClient.for_base_url(), catalog=_fixture_catalog(tmp_path))


def test_resolve_returns_single_match(tmp_path):
    nrl = _nrlx(tmp_path)

    config = nrl.resolve_sensor(manufacturer="Streckeisen", model="STS-1")

    assert config.instconfig == "sensor_Streckeisen_STS-1_LP360"


def test_resolve_raises_not_found(tmp_path):
    nrl = _nrlx(tmp_path)

    with pytest.raises(NrlxResponseError, match="No sensor configuration found"):
        nrl.resolve_sensor(manufacturer="Nonexistent")


def test_resolve_raises_ambiguous_lists_candidates(tmp_path):
    nrl = _nrlx(tmp_path)

    with pytest.raises(NrlxResponseError) as exc_info:
        nrl.resolve_sensor(manufacturer="Streckeisen", model="STS-2")

    message = str(exc_info.value)
    assert "Ambiguous sensor selection: 2 configurations match" in message
    assert "sensor_Streckeisen_STS-2_LP120_SG1500" in message
    assert "sensor_Streckeisen_STS-2_LP120_SG750" in message


def test_resolve_sensor_and_datalogger_wrappers(tmp_path):
    nrl = _nrlx(tmp_path)

    sensor_config = nrl.resolve_sensor(manufacturer="Streckeisen", model="STS-1")
    datalogger_config = nrl.resolve_datalogger(manufacturer="Quanterra", model="Q330")

    assert sensor_config.element == "sensor"
    assert datalogger_config.element == "datalogger"


def test_resolve_with_keys_narrows_to_unique(tmp_path):
    nrl = _nrlx(tmp_path)

    # "STS-2" alone is ambiguous (two gains); a parameter-value key settles it.
    config = nrl.resolve_sensor(keys=["streckeisen", "STS-2", "1500"])

    assert config.instconfig == "sensor_Streckeisen_STS-2_LP120_SG1500"


def test_resolve_with_keys_matches_parameter_values(tmp_path):
    nrl = _nrlx(tmp_path)

    config = nrl.resolve_datalogger(keys=["40Vpp"])

    assert config.instconfig == "datalogger_Quanterra_Q330_FV40Vpp_FR100"


def test_resolve_with_keys_ambiguous_raises(tmp_path):
    nrl = _nrlx(tmp_path)

    with pytest.raises(NrlxResponseError, match="Ambiguous sensor selection"):
        nrl.resolve_sensor(keys=["STS-2"])


def test_resolve_with_keys_no_match_raises(tmp_path):
    nrl = _nrlx(tmp_path)

    with pytest.raises(NrlxResponseError, match="No sensor configuration found"):
        nrl.resolve_sensor(keys=["STS-2", "does-not-exist"])


def test_combine_params_colon_joins_sensor_and_datalogger():
    params = Nrlx._combine_params(
        "sensor_A", "datalogger_B",
        format=ResponseFormat.STATIONXML, compress=False,
        network=None, station=None, location=None, channel=None,
        starttime=None, endtime=None,
    )

    assert params["instconfig"] == "sensor_A:datalogger_B"


def test_combine_params_omits_datalogger_when_none():
    params = Nrlx._combine_params(
        "sensor_A", None,
        format=ResponseFormat.STATIONXML, compress=False,
        network=None, station=None, location=None, channel=None,
        starttime=None, endtime=None,
    )

    assert params["instconfig"] == "sensor_A"


def test_combine_params_appends_zip_suffix():
    params = Nrlx._combine_params(
        "sensor_A", None,
        format=ResponseFormat.RESP, compress=True,
        network=None, station=None, location=None, channel=None,
        starttime=None, endtime=None,
    )

    assert params["format"] == "resp.zip"


def test_combine_params_always_sets_nodata_404():
    params = Nrlx._combine_params(
        "sensor_A", None,
        format=ResponseFormat.STATIONXML, compress=False,
        network=None, station=None, location=None, channel=None,
        starttime=None, endtime=None,
    )

    assert params["nodata"] == 404


def test_combine_params_includes_optional_filters():
    params = Nrlx._combine_params(
        "sensor_A", None,
        format=ResponseFormat.STATIONXML, compress=False,
        network="XX", station="YY", location="00", channel="ZZZ",
        starttime="2021-01-01", endtime=None,
    )

    assert params["network"] == "XX"
    assert params["station"] == "YY"
    assert params["location"] == "00"
    assert params["channel"] == "ZZZ"
    assert params["starttime"] == "2021-01-01"
    assert "endtime" not in params


class _FakeResponse:
    status_code = 200
    content = b"fake-response-bytes"

    def raise_for_status(self) -> None:
        return None


def test_sync_downloads_catalog_and_returns_ready_nrlx(tmp_path, monkeypatch):
    config = {"instconfig": "sensor_Streckeisen_STS-2_X", "version": "1"}
    model = {"name": "STS-2", "configuration": [config]}
    manufacturer = {"name": "Streckeisen", "model": [model]}
    element = {"name": "sensor", "manufacturer": [manufacturer]}
    catalog_bytes = json.dumps(
        {"NRLCatalog": {"formatversion": 1.0, "element": [element]}}
    ).encode("utf-8")

    class _CatalogResponse:
        status_code = 200
        content = catalog_bytes

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "nrlx.client.httpx.get",
        lambda url, params=None, timeout=None: _CatalogResponse(),
    )

    nrl = Nrlx.sync(tmp_path)

    assert isinstance(nrl, Nrlx)
    assert (tmp_path / "nrl" / "catalog.json").exists()
    assert nrl.catalog.configuration_count == 1
    assert nrl.resolve_sensor(model="STS-2").instconfig == "sensor_Streckeisen_STS-2_X"


def test_combine_hits_combine_endpoint_and_keeps_bytes_in_memory(
    tmp_path, monkeypatch
):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse()

    monkeypatch.setattr("nrlx.client.httpx.get", fake_get)

    nrl = _nrlx(tmp_path)
    built = nrl.combine(
        sensor_instconfig="sensor_Streckeisen_STS-1_LP360",
        datalogger_instconfig="datalogger_Quanterra_Q330_FV40Vpp_FR100",
    )

    assert isinstance(built, BuiltResponse)
    assert built.content == b"fake-response-bytes"
    assert built.format is ResponseFormat.STATIONXML
    assert captured["url"].endswith("combine")
    assert captured["params"]["instconfig"] == (
        "sensor_Streckeisen_STS-1_LP360:datalogger_Quanterra_Q330_FV40Vpp_FR100"
    )


def test_combine_resolves_keys_internally(tmp_path, monkeypatch):
    captured = {}

    def fake_get(url, params=None, timeout=None):
        captured["params"] = params
        return _FakeResponse()

    monkeypatch.setattr("nrlx.client.httpx.get", fake_get)

    nrl = _nrlx(tmp_path)
    nrl.combine(
        sensor_keys=["STS-2", "1500"],
        datalogger_keys=["40Vpp"],
    )

    assert captured["params"]["instconfig"] == (
        "sensor_Streckeisen_STS-2_LP120_SG1500"
        ":datalogger_Quanterra_Q330_FV40Vpp_FR100"
    )


def test_combine_requires_a_sensor_selection(tmp_path):
    nrl = _nrlx(tmp_path)

    with pytest.raises(NrlxResponseError, match="needs sensor_instconfig"):
        nrl.combine()


def test_combine_rejects_contradictory_sensor_selection(tmp_path):
    nrl = _nrlx(tmp_path)

    with pytest.raises(NrlxResponseError, match="not both"):
        nrl.combine(sensor_instconfig="sensor_A", sensor_keys=["sensor"])


def test_built_response_save_writes_file(tmp_path):
    built = BuiltResponse(
        content=b"payload",
        format=ResponseFormat.STATIONXML,
        instconfig="sensor_A",
    )
    output_file = tmp_path / "sub" / "response.xml"

    saved_path = built.save(output_file)

    assert saved_path == output_file
    assert output_file.read_bytes() == b"payload"


def test_built_response_converters_reject_non_stationxml(tmp_path):
    built = BuiltResponse(
        content=b"payload", format=ResponseFormat.RESP, instconfig="sensor_A"
    )

    with pytest.raises(NrlxResponseError, match="needs an uncompressed stationxml"):
        built.to_response()
