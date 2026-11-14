"""Requests to the NRL web service"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urljoin

import httpx

# the IRIS services moved to EarthScope, service.iris.edu redirects here
DEFAULT_BASE_URL = "https://service.earthscope.org/irisws/nrl/1/"
DEFAULT_TIMEOUT = 30.0


def get_url(base_url: str, path: str) -> str:
    """URL of an endpoint of the NRL service

    The base URL gets a trailing slash, so that the path is joined after its last
    segment instead of replacing it.

    Args:
        base_url: base URL of the service.
        path: endpoint, for example catalog.

    Returns:
        URL of the endpoint.


    """
    base = base_url if base_url.endswith("/") else f"{base_url}/"
    url = urljoin(base, path.lstrip("/"))

    return url


def get(
    base_url: str,
    path: str,
    params: dict[str, str | int] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> bytes:
    """Content of a GET request to an endpoint of the NRL service

    Args:
        base_url: base URL of the service.
        path: endpoint, for example catalog.
        params: query parameters, None for no parameters.
        timeout: timeout of the request in seconds.

    Returns:
        content of the answer.

    Raises:
        httpx.HTTPError: if the service cannot be reached or answers with an error
            status.


    """
    # httpx does not follow the redirects by default: a moved endpoint would be a
    # 301 error
    response = httpx.get(
        get_url(base_url, path),
        params=params,
        timeout=timeout,
        follow_redirects=True,
    )
    response.raise_for_status()

    return response.content


def download(
    base_url: str,
    path: str,
    params: dict[str, str | int] | None,
    target: Path,
    timeout: float = DEFAULT_TIMEOUT,
) -> Path:
    """Content of a GET request to an endpoint, written to a file as it arrives

    For the large answers (the whole NRL is 300 MB), which get would hold in memory.

    Args:
        base_url: base URL of the service.
        path: endpoint, for example combine.
        params: query parameters, None for no parameters.
        target: file to write, replaced if it exists.
        timeout: timeout of each step of the request in seconds.

    Returns:
        the file written.

    Raises:
        httpx.HTTPError: if the service cannot be reached or answers with an error
            status.
        OSError: if the file cannot be written.


    """
    with httpx.stream(
        "GET",
        get_url(base_url, path),
        params=params,
        timeout=timeout,
        follow_redirects=True,
    ) as response:
        response.raise_for_status()
        with target.open("wb") as file:
            for chunk in response.iter_bytes():
                file.write(chunk)

    return target
