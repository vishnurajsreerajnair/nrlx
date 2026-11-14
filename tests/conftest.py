from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
import pytest
from obspy import Inventory
from obspy.core.inventory import Channel, Network, Station
from obspy.core.inventory.response import (
    InstrumentSensitivity,
    PolesZerosResponseStage,
    Response,
)

from nrlx.io.cache import decode_catalog, decode_prefixes
from nrlx.models.catalog import Catalog
from nrlx.models.nrlx import Nrlx

DATA_DIR = Path(__file__).parent / "data"


@dataclass
class FakeRequest:
    """A request received by the fake service"""

    url: str
    params: dict[str, str | int] | None
    follow_redirects: bool


@dataclass
class FakeAnswer:
    """Answer of the fake service, as the httpx response"""

    content: bytes
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://fake.nrl/")
            raise httpx.HTTPStatusError(
                f"Server error '{self.status_code}'",
                request=request,
                response=httpx.Response(self.status_code, request=request),
            )


@dataclass
class FakeService:
    """Fake NRL service, answering each endpoint with its content

    The endpoints without content answer empty, and status_code applies to all of
    them. The requests are recorded in order.


    """

    contents: dict[str, bytes] = field(default_factory=dict)
    status_code: int = 200
    requests: list[FakeRequest] = field(default_factory=list)

    def get(
        self,
        url: str,
        params: dict[str, str | int] | None = None,
        timeout: float | None = None,
        follow_redirects: bool = False,
    ) -> FakeAnswer:
        self.requests.append(FakeRequest(url, params, follow_redirects))
        endpoint = url.rstrip("/").rsplit("/", 1)[-1]
        answer = FakeAnswer(self.contents.get(endpoint, b""), self.status_code)

        return answer


@pytest.fixture
def fake_service(monkeypatch) -> FakeService:
    """Fake NRL service in place of httpx.get"""
    service = FakeService()
    monkeypatch.setattr("nrlx.io.service.httpx.get", service.get)

    return service


# catalog
@pytest.fixture
def catalog_content() -> bytes:
    """JSON catalog with 2 elements, 3 manufacturers, 4 models and 5 configurations:
    Streckeisen STS-2 (SG1500 and SG750, with Sensitivity), STS-1, Nanometrics
    Trillium 120 sensors and a Quanterra Q330 datalogger (with Full-Scale_Voltage)"""
    return (DATA_DIR / "valid_catalog.json").read_bytes()


@pytest.fixture
def catalog(catalog_content) -> Catalog:
    """The decoded catalog of catalog_content"""
    return decode_catalog(catalog_content)


@pytest.fixture
def prefixes_content() -> bytes:
    """JSON code table with 4 codes, FR, FV, LP and SG (with a field added upstream)"""
    return (DATA_DIR / "valid_prefixes.json").read_bytes()


@pytest.fixture
def cache_root(tmp_path, catalog_content, prefixes_content) -> Path:
    """Cache root folder with catalog_content and prefixes_content synced"""
    root = tmp_path / "cache"
    (root / "nrl").mkdir(parents=True)
    (root / "nrl" / "catalog.json").write_bytes(catalog_content)
    (root / "nrl" / "prefixes.json").write_bytes(prefixes_content)

    return root


@pytest.fixture
def nrl(catalog, prefixes_content) -> Nrlx:
    """Nrlx with the catalog and the code table, on the default service"""
    return Nrlx(catalog=catalog, prefixes=decode_prefixes(prefixes_content))


# responses
@pytest.fixture
def valid_response_xml() -> Path:
    """Path of a minimal StationXML response, XX.YY.00.ZZZ"""
    return DATA_DIR / "valid_response.xml"


@pytest.fixture
def valid_response_resp() -> Path:
    """Path of a minimal RESP response, YY.00.ZZZ"""
    return DATA_DIR / "valid_response.resp"


@pytest.fixture
def make_stationxml() -> Callable[[str], bytes]:
    """Factory of single-channel StationXML documents of XY.MYSTN, with a poles and
    zeros stage of gain 1500 V/(m/s)"""

    def make(channel_code: str) -> bytes:
        stage = PolesZerosResponseStage(
            stage_sequence_number=1,
            stage_gain=1500.0,
            stage_gain_frequency=1.0,
            input_units="M/S",
            output_units="V",
            pz_transfer_function_type="LAPLACE (RADIANS/SECOND)",
            normalization_frequency=1.0,
            zeros=[0j, 0j],
            poles=[-0.037 + 0.037j, -0.037 - 0.037j],
            normalization_factor=1.0,
        )
        response = Response(
            instrument_sensitivity=InstrumentSensitivity(1500.0, 1.0, "M/S", "V"),
            response_stages=[stage],
        )
        channel = Channel(channel_code, "", 0.0, 0.0, 0.0, 0.0, response=response)
        station = Station("MYSTN", 0.0, 0.0, 0.0, channels=[channel])
        inventory = Inventory(
            networks=[Network("XY", stations=[station])], source="nrlx tests"
        )

        buffer = io.BytesIO()
        inventory.write(buffer, format="STATIONXML")

        return buffer.getvalue()

    return make
