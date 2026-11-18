"""Golden tests: the commands give the same results as nrlx 0.3.0b1

Each case runs commands of nrlx in an empty folder, with the frozen cache of
tests/data/golden/cache (a catalog of a few models, the code table and some files of
the local copy) and a fake service answering with the answers the real service gave
when the case was recorded. What the commands print and every file they write are
compared with tests/data/golden/expected/CASE: the numbers within a relative
tolerance, the dates and the versions of nrlx and obspy masked.

The expected results were recorded with nrlx 0.3.0b1. To record them again, on
purpose and with a reason in the commit (this sends requests to the real service):

    NRLX_GOLDEN_RECORD=1 pytest tests/entrypoints/test_golden


"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx
import obspy
import pytest
from typer.testing import CliRunner

import nrlx
from nrlx.tools.cmd import app

GOLDEN_DIR = Path(__file__).parents[2] / "data" / "golden"
SERVICE_DIR = GOLDEN_DIR / "service"
EXPECTED_DIR = GOLDEN_DIR / "expected"
META_FILE = GOLDEN_DIR / "meta.json"

RECORD = os.environ.get("NRLX_GOLDEN_RECORD") == "1"

# the real httpx functions, before any test replaces them
REAL_GET = httpx.get
REAL_STREAM = httpx.stream

# relative tolerance of the numbers, and absolute one around zero
REL_TOL = 1e-9
ABS_TOL = 1e-15

# a number in a text: integer, decimal or exponent
NUMBER = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?"

# dates and times: ISO (StationXML, the database) and SEED (RESP)
DATES = [
    r"\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?",
    r"\d{4},\d{3}(?:,\d{2}:\d{2}:\d{2}(?:\.\d+)?)?",
]

# the parts of the cases
STS2 = "sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel"
Q330HR = "datalogger_Quanterra_Q330HR_PG1_FR100_ADHR_LRbelow20_DENone"
TC120 = "sensor_Nanometrics_TrilliumCompact120_SG754_LP120_STgroundVel"
CENTAUR40 = "datalogger_Nanometrics_Centaur_FV40Vpp_FR100_DF0.001_FPMinimum"
TELLUS = "sensor_Lunitek_TELLUS_LP1_SG400_STgroundVel"
CENTAUR2 = "datalogger_Nanometrics_Centaur_FV2Vpp_FR100_DFOff_FPLinear"
CMG40T = "sensor_Guralp_CMG-40T_LP30_HF50_SG1600_STgroundVel"
DM24 = "datalogger_Guralp_CMG-DM24-Mk3-Fixed_TL77_TP400-100-20-10-2-1_FR100"
L22D = "sensor_Sercel_L-22D_LF2_RC5470_RS20000_SG87.9_STgroundVel"
RT130 = "datalogger_REFTEK_130-01_PG32_FR100"
EPISENSOR = (
    "sensor_Kinemetrics_Episensor-ES-T_CG4g_FV10Vp_OWSingle-ended_HF200_SG0.2549"
    "_STgroundAccel"
)
BASALT = "datalogger_Kinemetrics_Basalt_PG8_FV10Vpp_FR200_FPCausal"
GS11D = "sensor_GeoSpace_GS-11D_LF10_RC380_RS887_SG22.3_STgroundVel"
ATLAS = "datalogger_Lunitek_ATLAS_FV2.5Vpp_FR100_FPLinear"
GEM = "integrated_Gem_GemInfrasoundV1.0_AR0_LP26_FR100_SG286"
BALER = "soh_Quanterra_Q330HR-PacketBaler_CDInputVoltage_SG6.667_FR0.1"

# the options every command of a case shares
CACHE = ["--cache-root", "cache"]
LABELS = ["--network", "XY", "--location", "00"]
HH = ["--channels", "HHZ,HHN,HHE"]


@dataclass(frozen=True)
class Case:
    """A golden case: commands run in order in one folder

    Args:
        name: name of the case, the folder of its expected results.
        commands: the arguments of each nrlx command.
        inputs: files of tests/data/golden/inputs copied in the folder first.


    """

    name: str
    commands: list[list[str]]
    inputs: list[str]


CASES = [
    # responses built by the service, in the three formats
    Case(
        "build_sts2_q330hr_xml",
        [
            ["response", "--sensor", STS2, "--datalogger", Q330HR]
            + LABELS
            + ["--station", "T01"]
            + HH
            + ["-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_tc120_centaur_resp",
        [
            ["response", "--sensor", TC120, "--datalogger", CENTAUR40]
            + LABELS
            + ["--station", "T02"]
            + HH
            + ["-o", "out.resp"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_tellus_centaur_pz",
        [
            ["response", "--sensor", TELLUS, "--datalogger", CENTAUR2]
            + LABELS
            + ["--station", "T03"]
            + HH
            + ["-o", "out.pz"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_cmg40t_dm24_xml",
        [
            ["response", "--sensor", CMG40T, "--datalogger", DM24]
            + LABELS
            + ["--station", "T04"]
            + HH
            + ["-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_l22d_rt130_xml",
        [
            ["response", "--sensor", L22D, "--datalogger", RT130]
            + LABELS
            + ["--station", "T05"]
            + ["--channels", "EHZ,EHN,EHE", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_episensor_basalt_xml",
        [
            ["response", "--sensor", EPISENSOR, "--datalogger", BASALT]
            + LABELS
            + ["--station", "T06"]
            + ["--channels", "HNZ,HNN,HNE", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_gs11d_atlas_xml",
        [
            ["response", "--sensor", GS11D, "--datalogger", ATLAS]
            + LABELS
            + ["--station", "T07"]
            + ["--channels", "EHZ", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_split_xml",
        [
            ["response", "--sensor", TC120, "--datalogger", CENTAUR40]
            + LABELS
            + ["--station", "T08"]
            + HH
            + ["--split", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_integrated_xml",
        [
            ["response", "--integrated", GEM]
            + LABELS
            + ["--station", "T09", "--channels", "BDF", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "build_soh_xml",
        [
            ["response", "--soh", BALER]
            + LABELS
            + ["--station", "T10", "--channels", "VEI", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    # responses built by nrlx from the local copy and from files
    Case(
        "local_sts2_q330hr_xml",
        [
            ["response", "--sensor", STS2, "--datalogger", Q330HR]
            + LABELS
            + ["--station", "T11"]
            + HH
            + ["--source", "local", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "local_cmg40t_dm24_resp",
        [
            ["response", "--sensor", CMG40T, "--datalogger", DM24]
            + LABELS
            + ["--station", "T12"]
            + HH
            + ["--source", "local", "-o", "out.resp"]
            + CACHE
        ],
        [],
    ),
    Case(
        "local_sensor_alone_xml",
        [
            ["response", "--sensor", STS2]
            + LABELS
            + ["--station", "T13", "--channels", "HHZ"]
            + ["--source", "local", "-o", "out.xml"]
            + CACHE
        ],
        [],
    ),
    Case(
        "file_sensor_centaur_xml",
        [
            ["response", "--sensor", STS2, "--datalogger", Q330HR]
            + LABELS
            + ["--station", "T14"]
            + HH
            + ["-o", "first.xml"]
            + CACHE,
            ["response", "--sensor-file", "first.xml#XY.T14.00.HHZ"]
            + ["--datalogger", CENTAUR40]
            + LABELS
            + ["--station", "T15", "--channels", "HHZ", "-o", "out.xml"]
            + CACHE,
        ],
        [],
    ),
    # exploring the catalog
    Case("explore_catalog", [["response"] + CACHE], []),
    Case("explore_bare_keys", [["response", "STS-2"] + CACHE], []),
    Case(
        "explore_still_varying",
        [
            ["response", "--sensor", "STS-2,SG=1500", "--datalogger", "Q330HR,FR=100"]
            + CACHE
        ],
        [],
    ),
    Case(
        "explore_unique_line",
        [["response", "--sensor", STS2, "--datalogger", Q330HR] + HH + CACHE],
        [],
    ),
    Case("explore_codes", [["prefixes"] + CACHE, ["prefixes", "corner"] + CACHE], []),
    # checking files
    Case(
        "check_built_files",
        [
            ["response", "--sensor", STS2, "--datalogger", Q330HR]
            + LABELS
            + ["--station", "T16"]
            + HH
            + ["-o", "out.xml"]
            + CACHE,
            ["doctor", "out.xml", "--all"] + CACHE,
            ["response", "--sensor", TELLUS, "--datalogger", CENTAUR2]
            + LABELS
            + ["--station", "T17", "--channels", "HHZ", "-o", "out.pz"]
            + CACHE,
            ["doctor", "out.pz"] + CACHE,
        ],
        [],
    ),
    Case(
        "check_wrong_sensitivity",
        [["doctor", "wrong_sensitivity.xml", "--no-nominal"] + CACHE],
        ["wrong_sensitivity.xml"],
    ),
    Case(
        "check_dataless",
        [["doctor", "sts2_q330.dataless", "--no-nominal", "--all"] + CACHE],
        ["sts2_q330.dataless"],
    ),
    # converting files
    Case(
        "convert_formats",
        [
            ["convert", "sts2_q330.dataless", "-o", "from_dataless.xml"],
            ["convert", "from_dataless.xml", "-o", "from_xml.resp"],
            ["convert", "from_dataless.xml", "-o", "from_xml.pz"],
            ["convert", "from_xml.resp", "--split", "-o", "split.xml"],
        ],
        ["sts2_q330.dataless"],
    ),
    # the assets database
    Case(
        "assets_lifecycle",
        [
            ["response", "--sensor", STS2, "--datalogger", Q330HR]
            + LABELS
            + ["--station", "T18"]
            + HH
            + ["-o", "a.xml"]
            + CACHE,
            ["response", "--sensor", TC120, "--datalogger", CENTAUR40]
            + LABELS
            + ["--station", "T18"]
            + HH
            + ["-o", "b.xml"]
            + CACHE,
            ["assets", "add", "a.xml", "--db", "assets.sqlite"],
            ["assets", "add", "a.xml", "--db", "assets.sqlite"],
            ["assets", "add", "b.xml", "--db", "assets.sqlite"],
            ["assets", "add", "b.xml", "--uid", "SPARE", "--db", "assets.sqlite"],
            ["assets", "list", "--db", "assets.sqlite"],
            ["assets", "list", "T18", "--db", "assets.sqlite"],
            ["assets", "get", "T18", "-o", "latest.resp", "--db", "assets.sqlite"],
            ["assets", "get", "T18", "--version", "1", "-o", "v1.xml"]
            + ["--db", "assets.sqlite"],
            ["assets", "deprecate", "T18", "--version", "2", "--db", "assets.sqlite"],
            ["assets", "list", "T18", "--db", "assets.sqlite"],
            ["assets", "export", "exported", "--db", "assets.sqlite"],
            ["assets", "import", "exported", "--db", "copy.sqlite"],
            ["assets", "list", "--db", "copy.sqlite"],
        ],
        [],
    ),
]


def request_key(url: str, params: dict[str, str | int] | None) -> str:
    """Name of the recorded answer of a request: its endpoint and a hash of it

    Args:
        url: URL of the request.
        params: query parameters, None for none.

    Returns:
        endpoint_HASH, the same for the same endpoint and parameters in any order.


    """
    endpoint = url.rstrip("/").rsplit("/", 1)[-1]
    text = json.dumps([endpoint, sorted((params or {}).items())])
    key = f"{endpoint}_{hashlib.sha256(text.encode()).hexdigest()[:16]}"

    return key


class GoldenService:
    """httpx.get and httpx.stream answering with the recorded answers

    In record mode, the real service answers and its answers are written to
    tests/data/golden/service, with an index of the requests.


    """

    def __init__(self) -> None:
        self.index_file = SERVICE_DIR / "index.json"
        self.index: dict[str, dict[str, object]] = (
            json.loads(self.index_file.read_text()) if self.index_file.is_file() else {}
        )

    def content(self, url: str, params: dict[str, str | int] | None) -> bytes:
        """Answer of a request, recorded or replayed

        Args:
            url: URL of the request.
            params: query parameters.

        Returns:
            the content of the answer.

        Raises:
            AssertionError: when replaying a request that was never recorded.


        """
        key = request_key(url, params)
        answer_file = SERVICE_DIR / f"{key}.bin"
        if RECORD:
            # the real service, its answer kept for the replays
            response = REAL_GET(url, params=params, timeout=60, follow_redirects=True)
            response.raise_for_status()
            SERVICE_DIR.mkdir(parents=True, exist_ok=True)
            answer_file.write_bytes(response.content)
            self.index[key] = {"url": url, "params": params}
            self.index_file.write_text(json.dumps(self.index, indent=2, sort_keys=True))
        assert answer_file.is_file(), f"request not recorded: {url} {params}"
        content = answer_file.read_bytes()

        return content

    def get(
        self,
        url: str,
        params: dict[str, str | int] | None = None,
        timeout: float | None = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        request = httpx.Request("GET", url, params=params)
        content = self.content(url, params)
        response = httpx.Response(200, content=content, request=request)

        return response

    def stream(
        self,
        method: str,
        url: str,
        params: dict[str, str | int] | None = None,
        timeout: float | None = None,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        # nrlx streams only the whole NRL, which no case downloads
        raise AssertionError(f"no golden case downloads the NRL: {url}")


def recorded_versions() -> dict[str, str]:
    """Versions of nrlx and obspy that recorded the expected results

    Returns:
        the versions by package, the running ones in record mode.


    """
    running = {"nrlx": nrlx.__version__, "obspy": obspy.__version__}
    if RECORD:
        META_FILE.write_text(json.dumps(running, indent=2))
    versions: dict[str, str] = json.loads(META_FILE.read_text())

    return versions


def mask(text: str, versions: dict[str, str], folder: Path) -> str:
    """Text with what changes on its own replaced: folder, versions, dates

    Args:
        text: output of a command or content of a file.
        versions: versions of nrlx and obspy written in the text.
        folder: folder the case ran in.

    Returns:
        the masked text.


    """
    masked = text.replace(str(folder), "<FOLDER>")
    for package, version in versions.items():
        masked = masked.replace(version, f"<{package.upper()}>")
    for pattern in DATES:
        masked = re.sub(pattern, "<DATE>", masked)

    return masked


def compare_text(expected: str, actual: str, name: str) -> list[str]:
    """Differences of two masked texts, line by line, numbers within tolerance

    Args:
        expected: expected text.
        actual: text of the run.
        name: name of the output, for the messages.

    Returns:
        the differences, empty when the texts agree.


    """
    expected_lines = expected.splitlines()
    actual_lines = actual.splitlines()
    differences = []
    if len(expected_lines) != len(actual_lines):
        differences.append(
            f"{name}: {len(actual_lines)} lines instead of {len(expected_lines)}"
        )
    # the lines both have, when the counts differ
    pairs = zip(expected_lines, actual_lines, strict=False)
    for number, (want, got) in enumerate(pairs, 1):
        # the odd pieces of the split are the numbers
        want_pieces = re.split(f"({NUMBER})", want)
        got_pieces = re.split(f"({NUMBER})", got)
        agree = len(want_pieces) == len(got_pieces) and all(
            (
                math.isclose(float(a), float(b), rel_tol=REL_TOL, abs_tol=ABS_TOL)
                if position % 2
                else a == b
            )
            for position, (a, b) in enumerate(zip(want_pieces, got_pieces, strict=True))
        )
        if not agree:
            differences.append(
                f"{name}:{number}\n  expected: {want}\n  got:      {got}"
            )

    return differences


def output_files(folder: Path, inputs: list[str]) -> list[Path]:
    """Files written by the commands of a case, relative to its folder

    Args:
        folder: folder the case ran in.
        inputs: the input files copied in it.

    Returns:
        the files, sorted, without the cache, the inputs and the databases.


    """
    files = sorted(
        path.relative_to(folder)
        for path in folder.rglob("*")
        if path.is_file()
        and path.relative_to(folder).parts[0] != "cache"
        and path.name not in inputs
        and path.suffix != ".sqlite"
    )

    return files


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_golden(case, tmp_path, monkeypatch):
    service = GoldenService()
    monkeypatch.setattr(httpx, "get", service.get)
    monkeypatch.setattr(httpx, "stream", service.stream)
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.chdir(tmp_path)
    shutil.copytree(GOLDEN_DIR / "cache", tmp_path / "cache")
    for name in case.inputs:
        shutil.copy(GOLDEN_DIR / "inputs" / name, tmp_path / name)
    versions = recorded_versions()
    running = {"nrlx": nrlx.__version__, "obspy": obspy.__version__}

    # every command, its exit code and what it prints, in one transcript
    runner = CliRunner()
    transcript = []
    for arguments in case.commands:
        result = runner.invoke(app, arguments, terminal_width=200)
        transcript.append(f"$ nrlx {' '.join(arguments)}")
        transcript.append(f"exit {result.exit_code}")
        transcript.append(result.output)
    actual = {"transcript.txt": mask("\n".join(transcript), running, tmp_path)}
    for path in output_files(tmp_path, case.inputs):
        actual[str(path)] = mask((tmp_path / path).read_text(), running, tmp_path)

    expected_dir = EXPECTED_DIR / case.name
    if RECORD:
        shutil.rmtree(expected_dir, ignore_errors=True)
        for name, text in actual.items():
            (expected_dir / name).parent.mkdir(parents=True, exist_ok=True)
            (expected_dir / name).write_text(text)

    # the expected results, masked with the versions that recorded them
    expected = {
        str(path.relative_to(expected_dir)): mask(path.read_text(), versions, tmp_path)
        for path in sorted(expected_dir.rglob("*"))
        if path.is_file()
    }
    assert sorted(actual) == sorted(expected), "the files written differ"
    differences = [
        difference
        for name in sorted(expected)
        for difference in compare_text(expected[name], actual[name], name)
    ]
    assert not differences, "\n".join(differences[:20])
