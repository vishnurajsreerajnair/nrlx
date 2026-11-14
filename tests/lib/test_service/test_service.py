from __future__ import annotations

import httpx
import pytest

from nrlx.io.service import DEFAULT_BASE_URL, download, get, get_url


@pytest.mark.parametrize(
    "base_url",
    ["https://isamgeo.in/nrl", "https://isamgeo.in/nrl/"],
)
@pytest.mark.parametrize("path", ["catalog", "/catalog"])
def test_url_joins_after_the_last_segment(base_url, path):
    assert get_url(base_url, path) == "https://isamgeo.in/nrl/catalog"


def test_get_returns_the_content_following_redirects(fake_service):
    fake_service.contents["catalog"] = b"payload"

    content = get(DEFAULT_BASE_URL, "catalog", {"nodata": 404})

    assert content == b"payload"
    [request] = fake_service.requests
    assert request.url == f"{DEFAULT_BASE_URL}catalog"
    assert request.params == {"nodata": 404}
    assert request.follow_redirects


def test_get_raises_on_error_status(fake_service):
    fake_service.status_code = 404

    with pytest.raises(httpx.HTTPStatusError):
        get(DEFAULT_BASE_URL, "catalog")


def test_download_writes_the_stream_to_a_file(fake_service, tmp_path):
    fake_service.contents["combine"] = b"a large answer"

    target = download(DEFAULT_BASE_URL, "combine", {"nodata": 404}, tmp_path / "f")

    assert target.read_bytes() == b"a large answer"
    [request] = fake_service.requests
    assert request.params == {"nodata": 404}
    assert request.follow_redirects


def test_download_raises_on_error_status(fake_service, tmp_path):
    fake_service.status_code = 503

    with pytest.raises(httpx.HTTPStatusError):
        download(DEFAULT_BASE_URL, "combine", None, tmp_path / "f")
