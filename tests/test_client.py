from __future__ import annotations

from nrlx.client import DEFAULT_NRL_BASE_URL, NRLClient


def test_client_normalizes_base_url():
    client = NRLClient(base_url="https://isamgeo.in/nrl")

    assert client.base_url == "https://isamgeo.in/nrl/"


def test_client_builds_url():
    client = NRLClient(base_url="https://isamgeo.in/nrl/")

    assert client.build_url("catalog") == "https://isamgeo.in/nrl/catalog"
    assert client.build_url("/catalog") == "https://isamgeo.in/nrl/catalog"


def test_for_base_url_falls_back_to_default_when_omitted():
    client = NRLClient.for_base_url()

    assert client.base_url == DEFAULT_NRL_BASE_URL


def test_for_base_url_uses_given_url():
    client = NRLClient.for_base_url("https://isamgeo.in/nrl")

    assert client.base_url == "https://isamgeo.in/nrl/"