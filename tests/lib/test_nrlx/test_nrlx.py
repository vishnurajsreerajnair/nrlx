from __future__ import annotations

import pytest

from nrlx.io.cache import get_catalog_file, get_prefixes_file
from nrlx.models.nrlx import Nrlx
from nrlx.models.response import BuiltResponse


def test_from_cache(cache_root):
    nrl = Nrlx.from_cache(cache_root, base_url="https://isamgeo.in/nrl/")

    assert nrl.base_url == "https://isamgeo.in/nrl/"
    assert len(nrl.catalog.get_configurations()) == 5
    assert [prefix.prefix for prefix in nrl.prefixes] == ["FR", "FV", "LP", "SG"]


def test_from_cache_without_catalog_says_sync(tmp_path):
    with pytest.raises(FileNotFoundError, match="Run 'nrlx sync'"):
        Nrlx.from_cache(tmp_path)


def test_from_cache_without_code_table_says_sync(cache_root):
    get_prefixes_file(cache_root).unlink()

    with pytest.raises(FileNotFoundError, match="Code table not found"):
        Nrlx.from_cache(cache_root)


def test_sync_downloads_the_catalog_and_returns_a_ready_nrlx(
    tmp_path, fake_service, catalog_content, prefixes_content
):
    fake_service.contents["catalog"] = catalog_content
    fake_service.contents["prefix-lookup"] = prefixes_content

    nrl = Nrlx.sync(tmp_path)

    assert get_catalog_file(tmp_path).read_bytes() == catalog_content
    assert get_prefixes_file(tmp_path).read_bytes() == prefixes_content
    assert len(nrl.prefixes) == 4
    assert fake_service.requests[1].params == {"format": "json", "nodata": 404}
    assert nrl.catalog.resolve("sensor", model_name="STS-1").instconfig == (
        "sensor_Streckeisen_STS-1_LP360"
    )


def test_sync_keeps_the_previous_catalog_on_invalid_download(
    cache_root, fake_service, catalog_content
):
    fake_service.contents["catalog"] = b"<html>maintenance</html>"

    with pytest.raises(ValueError, match="Invalid catalog"):
        Nrlx.sync(cache_root)
    assert get_catalog_file(cache_root).read_bytes() == catalog_content


def test_sync_invalid_code_table_keeps_both_previous_files(
    cache_root, fake_service, catalog_content, prefixes_content
):
    fake_service.contents["catalog"] = catalog_content.replace(b"STS-1", b"STS-9")
    fake_service.contents["prefix-lookup"] = b"<html>maintenance</html>"

    with pytest.raises(ValueError, match="Invalid code table"):
        Nrlx.sync(cache_root)
    assert get_catalog_file(cache_root).read_bytes() == catalog_content
    assert get_prefixes_file(cache_root).read_bytes() == prefixes_content


def test_combine_requests_the_cascade_and_keeps_the_bytes_in_memory(nrl, fake_service):
    fake_service.contents["combine"] = b"fake-response-bytes"

    response = nrl.combine(
        sensor_instconfig="sensor_Streckeisen_STS-1_LP360",
        datalogger_instconfig="datalogger_Quanterra_Q330_FV40Vpp_FR100",
    )

    assert response == BuiltResponse(
        b"fake-response-bytes",
        "stationxml",
        "sensor_Streckeisen_STS-1_LP360:datalogger_Quanterra_Q330_FV40Vpp_FR100",
    )
    [request] = fake_service.requests
    assert request.url.endswith("/combine")
    assert request.params["instconfig"] == response.instconfig


def test_combine_resolves_the_keys(nrl, fake_service):
    nrl.combine(sensor_keys=["STS-2", "1500"], datalogger_keys=["40Vpp"])

    [request] = fake_service.requests
    assert request.params["instconfig"] == (
        "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
        ":datalogger_Quanterra_Q330_FV40Vpp_FR100"
    )


def test_combine_without_sensor_is_ambiguous(nrl, fake_service):
    with pytest.raises(LookupError, match="Ambiguous sensor selection"):
        nrl.combine()
    assert fake_service.requests == []


def test_combine_rejects_instconfig_and_keys(nrl):
    with pytest.raises(ValueError, match="not both"):
        nrl.combine(sensor_instconfig="sensor_A", sensor_keys=["sensor"])
