"""A thin HTTP client for the online NRL web service.

``NRLClient`` is a frozen, reusable value that knows the base URL and timeout;
it wraps ``httpx`` GET requests and turns transport errors into
:class:`~nrlx.exceptions.NrlxNetworkError`.


"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from nrlx.exceptions import NrlxError, NrlxNetworkError

DEFAULT_NRL_BASE_URL = "https://service.iris.edu/irisws/nrl/1/"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class NRLClient:
    """HTTP client for the online NRL web service.

    Args:
        base_url: Base URL for the NRL web service.
        timeout: Request timeout in seconds.


    """
    base_url: str = DEFAULT_NRL_BASE_URL
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        """Normalize client configuration after initialization."""

        # frozen=True blocks normal attribute assignment, even here in
        # __post_init__, so object.__setattr__ is the sanctioned bypass.
        object.__setattr__(self, "base_url", self._normalize_base_url(self.base_url))

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        """Return base_url with a trailing slash so relative paths join correctly."""
        return base_url if base_url.endswith("/") else f"{base_url}/"

    @classmethod
    def for_base_url(
        cls,
        base_url: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS
    ) -> NRLClient:
        """Build a client for an optional custom base URL.

        Args:
            base_url: Custom NRL service base URL. Falls back to the default
                online NRL endpoint when omitted.
            timeout: Request timeout in seconds.

        Returns:
            NRLClient configured with the resolved endpoint.


        """
        return cls(
            base_url=base_url or DEFAULT_NRL_BASE_URL,
            timeout=timeout
        )

    def build_url(self, path: str) -> str:
        """Build a full service URL from a relative endpoint path.

        Args:
            path: Relative service path, for example ``"catalog"``.

        Returns:
            Fully qualified URL.


        """
        return urljoin(self.base_url, path.lstrip("/"))

    def ping(self) -> bool:
        """Check whether the NRL service is reachable.

        Returns:
            True when the service responds successfully.

        Raises:
            NrlxNetworkError: If the service cannot be reached.


        """
        response = self.get("catalog")
        return response.status_code == 200

    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None
    ) -> httpx.Response:
        """Perform a checked HTTP GET request.

        Args:
            path: Relative service path.
            params: Optional query parameters.

        Returns:
            HTTP response object.

        Raises:
            NrlxNetworkError: If the request fails or returns an error status.


        """
        url = self.build_url(path)

        try:
            response = httpx.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise NrlxNetworkError(f"NRL request failed: {url}") from exc

        return response

    def download(
        self,
        path: str,
        output_file: Path,
        params: dict[str, Any] | None = None
    ) -> Path:
        """Download content from the NRL service to a local file.

        Args:
            path: Relative service path.
            output_file: Destination file path.
            params: Optional query parameters.

        Returns:
            Path to the downloaded file.

        Raises:
            NrlxNetworkError: If the HTTP request fails.
            NrlxError: If the response cannot be written to disk.


        """
        response = self.get(path, params=params)

        # The fetch succeeded here; a failure past this point is local I/O
        # (permissions, disk full), not a network problem - hence NrlxError.
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_bytes(response.content)
        except OSError as exc:
            raise NrlxError(f"Failed to write downloaded file: {output_file}") from exc

        return output_file
