"""End-to-end battery of nrlx assets through the commands, on random NRL pairs

The service builds the responses, with requests spaced by --pause seconds; the
assets go to databases of the output folder. Each case records the command, its
exit code and what it checks: the adds by nrlx response, the duplicates, the
variants, get in the three formats and by keys, a file not built by nrlx, the
deprecations and deletions, the export and import, concurrent adds, the errors.
Writes assets.json.

Example:

    python scripts/e2e/assets_battery.py --cache-root CACHE --out OUT


"""

from __future__ import annotations

import argparse
import random
import shutil
import sqlite3
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import msgspec
import numpy as np
import obspy
from common import curve, grid, run_nrlx
from obspy import Inventory

from nrlx.models.assets import Assets
from nrlx.models.nrlx import Nrlx
from nrlx.schema.asset import AssetRow

# the /combine endpoint of the service, for the file not built by nrlx
COMBINE_URL = "https://service.earthscope.org/irisws/nrl/1/combine"


class AssetCase(msgspec.Struct, kw_only=True):
    """A command, or a check on the files and the databases

    Args:
        group: the section of the battery.
        name: what it checks.
        command: the command, empty for a check without one.
        exit: its exit code.
        expected: the exit code expected.
        ok: whether the exit code and the check pass.
        detail: what the check found.
        output: the end of the output of the command.


    """

    group: str
    name: str
    command: str
    exit: int
    expected: int
    ok: bool
    detail: str
    output: str


class AssetsResult(msgspec.Struct, frozen=True, kw_only=True):
    """The result of the battery, assets.json

    Args:
        cases: the cases.
        requests: requests made to the service.
        rows: the rows of the main database at the end.


    """

    cases: list[AssetCase]
    requests: int
    rows: list[AssetRow]


def record(
    cases: list[AssetCase],
    group: str,
    name: str,
    arguments: list[str],
    expected: int,
    texts: list[str],
    stdin: str | None = None,
) -> tuple[int, str]:
    """Run nrlx, check its exit code and the texts its output must hold, and
    record the case

    Args:
        cases: the cases so far, the new one appended.
        group: the section of the battery.
        name: what it checks.
        arguments: arguments after nrlx.
        expected: the exit code expected.
        texts: texts the output must hold, when the exit code is the one
            expected.
        stdin: text on its standard input, None for none.

    Returns:
        the exit code and the output.


    """
    code, output = run_nrlx(arguments, stdin=stdin)
    missing = [text for text in texts if text not in output] if code == expected else []
    cases.append(
        AssetCase(
            group=group,
            name=name,
            command=f"nrlx {' '.join(arguments)}",
            exit=code,
            expected=expected,
            ok=code == expected and not missing,
            detail=f"missing {missing}" if missing else "",
            output=output.strip()[-400:],
        )
    )
    print("PASS" if cases[-1].ok else "FAIL", group, name, code, flush=True)

    return code, output


def check(cases: list[AssetCase], group: str, name: str, ok: bool, detail: str) -> None:
    """Record a check made without a command

    Args:
        cases: the cases so far, the new one appended.
        group: the section of the battery.
        name: what it checks.
        ok: whether it passes.
        detail: what it found.


    """
    cases.append(
        AssetCase(
            group=group,
            name=name,
            command="",
            exit=0,
            expected=0,
            ok=ok,
            detail=detail,
            output="",
        )
    )
    print("PASS" if ok else "FAIL", group, name, detail, flush=True)


def same_curve(reference: Inventory, other: Inventory) -> float:
    """Curve of the first channel of two inventories, on the grid of the first:
    obspy reads a RESP below 0.5 sps at 0 sps

    Args:
        reference: the inventory compared with.
        other: the inventory compared.

    Returns:
        the largest relative difference, where both are above zero.


    """
    first, second = reference[0][0][0], other[0][0][0]
    frequencies = grid(first.sample_rate)
    x, y = curve(first.response, frequencies), curve(second.response, frequencies)
    mask = (x > 0) & (y > 0)
    difference = float(np.max(np.abs(y[mask] / x[mask] - 1)))

    return difference


def main() -> None:
    """Run the battery: the arguments, the cases, assets.json in the output folder
    and a line per case on the standard output


    """
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261116)
    parser.add_argument("--stations", type=int, default=12)
    parser.add_argument("--pause", type=float, default=0.3)
    arguments = parser.parse_args()
    warnings.simplefilter("ignore")
    work = arguments.out / "assets"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    db = work / "assets.sqlite"
    on_db = ["--db", str(db)]
    common = ["--cache-root", str(arguments.cache_root)]
    cases: list[AssetCase] = list()
    requests = 0

    # random sensors and dataloggers from the seed, the datalogger with its model
    nrl = Nrlx.from_cache(arguments.cache_root)
    sensors, dataloggers = list(), list()
    for element, _, model, configuration in nrl.catalog.get_configurations():
        match element.name:
            case "sensor":
                sensors.append(configuration.instconfig)
            case "datalogger":
                dataloggers.append((model.name, configuration.instconfig))
    rng = random.Random(arguments.seed)
    picked_sensors = rng.sample(sensors, arguments.stations)
    picked_dataloggers = rng.sample(dataloggers, arguments.stations)
    assets = Assets(db=db, catalog=nrl.catalog, prefixes=nrl.prefixes)

    # nrlx response of a station, with --add-asset and -o, by the service
    def build(
        station: str, sensor: str, datalogger: str, extra: list[str]
    ) -> tuple[Path, list[str]]:
        path = work / f"{station}_{len(list(work.glob(f'{station}_*')))}.xml"
        build_arguments = [
            "response",
            "--sensor",
            sensor,
            "--datalogger",
            datalogger,
            "--network",
            "XY",
            "--station",
            station,
            "--location",
            "00",
            "--channels",
            "HHZ,HHN,HHE",
            "-o",
            str(path),
            "--add-asset",
            *on_db,
            *common,
            *extra,
        ]
        time.sleep(arguments.pause)

        return path, build_arguments

    # 1. one asset per station, written and added by nrlx response
    stations = list()
    for number, (sensor, (datalogger_model, datalogger)) in enumerate(
        zip(picked_sensors, picked_dataloggers, strict=True)
    ):
        station = f"A{number:02d}"
        path, build_arguments = build(station, sensor, datalogger, [])
        requests += 1
        code, _ = record(
            cases,
            "add",
            f"{station}: response --add-asset -o",
            build_arguments,
            0,
            [f"Added asset {station} v1"],
        )
        if code != 0:
            continue
        written = obspy.read_inventory(str(path))
        comments = {
            comment.value
            for net in written
            for sta in net
            for cha in sta
            for comment in cha.comments
            if comment.subject == "nrlx"
        }
        [row] = assets.list(station)
        stations.append((station, sensor, datalogger, datalogger_model, path))
        comment = next(iter(comments), "")
        check(
            cases,
            "provenance",
            f"{station}: comment and columns",
            len(comments) == 1
            and f"sensor={sensor}" in comment
            and f"datalogger={datalogger}" in comment
            and row.sensor == sensor
            and row.datalogger == datalogger
            and row.channels == [f"XY.{station}.00.{c}" for c in ("HHZ", "HHN", "HHE")]
            and row.sample_rate == written[0][0][0].sample_rate,
            comment[:160] if comment else "no comment",
        )

    # 2. the same build again: a note, no new version; the same from the local copy
    station, sensor, datalogger, _, _ = stations[0]
    _, build_arguments = build(station, sensor, datalogger, [])
    requests += 1
    record(
        cases,
        "duplicate",
        "same build again: note, exit 0",
        build_arguments,
        0,
        [f"{station} already has this response as v1: not added"],
    )
    _, build_arguments = build(station, sensor, datalogger, ["--source", "local"])
    record(cases, "duplicate", "same pair from the local copy", build_arguments, 0, [])
    versions = [row.version for row in assets.list(station)]
    cases[-1].detail = f"versions after the local build: {versions}"

    # 3. a second variant of four stations: another datalogger
    for station, sensor, datalogger, _, _ in stations[1:5]:
        second = rng.choice([i for _, i in dataloggers if i != datalogger])
        _, build_arguments = build(station, sensor, second, [])
        requests += 1
        record(
            cases,
            "variants",
            f"{station}: second variant",
            build_arguments,
            0,
            [f"Added asset {station} v2"],
        )
        out = ["-o", str(work / f"get_{station}.xml"), *on_db, *common]
        record(
            cases,
            "variants",
            f"{station}: get without keys lists the variants",
            ["assets", "get", station, *out],
            1,
            ["2 variants for these keys"],
        )
        record(
            cases,
            "variants",
            f"{station}: get by the instconfig of v1",
            ["assets", "get", station, datalogger, *out],
            0,
            [f"{station} v1 written"],
        )
        record(
            cases,
            "variants",
            f"{station}: get by the instconfig of v2",
            ["assets", "get", station, second, *out],
            0,
            [f"{station} v2 written"],
        )
        record(
            cases,
            "variants",
            f"{station}: get --version 1",
            ["assets", "get", station, "--version", "1", *out],
            0,
            [f"{station} v1 written"],
        )

    # 4. get in the three formats against the file nrlx response wrote, and by keys
    for station, _, _, datalogger_model, path in stations[5:]:
        for suffix in (".xml", ".resp", ".pz"):
            out_path = work / f"get_{station}{suffix}"
            code, output = record(
                cases,
                "get",
                f"{station}: get -o {suffix}",
                ["assets", "get", station, "-o", str(out_path), *on_db, *common],
                0,
                [],
            )
            if code == 0 and suffix != ".pz":
                difference = same_curve(
                    obspy.read_inventory(str(path)), obspy.read_inventory(str(out_path))
                )
                cases[-1].ok = difference <= 1e-9
                cases[-1].detail = f"curve vs the written file: {difference:.1e}"
            elif code == 0:
                notes = [
                    line for line in output.splitlines() if line.startswith("note:")
                ]
                cases[-1].detail = notes[0][:160] if notes else ""
        word = datalogger_model.split()[0]
        record(
            cases,
            "get",
            f"{station}: get by the datalogger model word {word!r}",
            [
                "assets",
                "get",
                station,
                word,
                "-o",
                str(work / "w.xml"),
                *on_db,
                *common,
            ],
            0,
            [],
        )
        rate = obspy.read_inventory(str(path))[0][0][0].sample_rate
        out = ["-o", str(work / "r.xml"), *on_db, *common]
        record(
            cases,
            "get",
            f"{station}: get rate={rate:g}",
            ["assets", "get", station, f"rate={rate:g}", *out],
            0,
            [],
        )
        record(
            cases,
            "get",
            f"{station}: get rate={rate * 2:g} matches nothing",
            ["assets", "get", station, f"rate={rate * 2:g}", *out],
            1,
            ["No version of"],
        )

    # 5. a file not built by nrlx: the service's own RESP, added under a serial
    _, sensor, datalogger, _, _ = stations[6]
    service_resp = work / "service.resp"
    time.sleep(arguments.pause)
    requests += 1
    answer = httpx.get(
        COMBINE_URL,
        params={
            "instconfig": f"{sensor}:{datalogger}",
            "format": "resp",
            "nodata": 404,
        },
        timeout=60,
    )
    service_resp.write_text(answer.raise_for_status().text)
    record(
        cases,
        "files",
        "add the service RESP without --uid (placeholder)",
        ["assets", "add", str(service_resp), *on_db],
        1,
        ["placeholder YY: give a UID"],
    )
    record(
        cases,
        "files",
        "add the service RESP as SN1234",
        ["assets", "add", str(service_resp), "--uid", "SN1234", *on_db],
        0,
        ["Added SN1234 v1"],
    )
    [serial] = assets.list("SN1234")
    check(
        cases,
        "files",
        "SN1234: no provenance, columns from the file",
        serial.sensor is None
        and serial.datalogger is None
        and serial.sample_rate is not None,
        f"rate {serial.sample_rate}, units {serial.input_units}",
    )
    record(
        cases,
        "files",
        "SN1234: a key on the NRL parts finds nothing",
        [
            "assets",
            "get",
            "SN1234",
            "STS-2",
            "-o",
            str(work / "s.xml"),
            *on_db,
            *common,
        ],
        1,
        ["No version of SN1234 in use"],
    )
    record(
        cases,
        "files",
        "add the same file again",
        ["assets", "add", str(service_resp), "--uid", "SN1234", *on_db],
        1,
        ["SN1234 already has this response"],
    )

    # 6. deprecate and delete
    station = stations[1][0]
    out = ["-o", str(work / "l.xml"), *on_db, *common]
    record(
        cases,
        "lifecycle",
        "deprecate v2",
        ["assets", "deprecate", station, "--version", "2", *on_db],
        0,
        [f"{station} v2 deprecated."],
    )
    record(
        cases,
        "lifecycle",
        "get without keys now takes v1",
        ["assets", "get", station, *out],
        0,
        [f"{station} v1 written"],
    )
    record(
        cases,
        "lifecycle",
        "deprecated v2 is still got by --version",
        ["assets", "get", station, "--version", "2", *out],
        0,
        [f"{station} v2 written"],
    )
    record(
        cases,
        "lifecycle",
        "undo",
        ["assets", "deprecate", station, "--version", "2", "--undo", *on_db],
        0,
        ["back in use"],
    )
    record(
        cases,
        "lifecycle",
        "list shows every version",
        ["assets", "list", *on_db],
        0,
        ["SN1234", "in use"],
    )
    record(
        cases,
        "lifecycle",
        "delete asks, answer no",
        ["assets", "delete", "SN1234", *on_db],
        0,
        ["Nothing deleted."],
        stdin="n\n",
    )
    record(
        cases,
        "lifecycle",
        "delete an unknown version",
        ["assets", "delete", "SN1234", "--version", "9", "--yes", *on_db],
        1,
        ["No version 9 of SN1234"],
    )

    # 7. export and import
    share = work / "share"
    record(
        cases,
        "share",
        "export",
        ["assets", "export", str(share), *on_db],
        0,
        ["Exported"],
    )
    total = len(assets.list())
    files = sorted(path.relative_to(share).as_posix() for path in share.rglob("*.xml"))
    check(
        cases,
        "share",
        "a file per version and the manifest",
        len(files) == total and (share / "manifest.json").is_file(),
        f"{len(files)} files for {total} versions",
    )
    record(
        cases,
        "share",
        "export into the same folder again",
        ["assets", "export", str(share), *on_db],
        1,
        ["is not empty"],
    )
    other = work / "colleague.sqlite"
    record(
        cases,
        "share",
        "import into a new database",
        ["assets", "import", str(share), "--db", str(other)],
        0,
        [f"Imported {total} versions, 0 already here"],
    )
    mine = [(row.uid, row.version, row.sha256) for row in assets.list()]
    theirs = [(row.uid, row.version, row.sha256) for row in Assets(db=other).list()]
    check(
        cases,
        "share",
        "the imported rows equal the exported ones",
        mine == theirs,
        f"{len(theirs)} rows",
    )
    record(
        cases,
        "share",
        "import the database itself again",
        ["assets", "import", str(db), "--db", str(other)],
        0,
        [f"Imported 0 versions, {total} already here"],
    )
    changed = share / stations[0][0] / "v1.xml"
    changed.write_text(
        changed.read_text().replace("<Latitude", "<!-- x --><Latitude", 1)
    )
    third = work / "third.sqlite"
    record(
        cases,
        "share",
        "a file changed after the export is refused",
        ["assets", "import", str(share), "--db", str(third)],
        1,
        ["changed since the export"],
    )
    cases[-1].detail = f"third.sqlite created: {third.exists()}"
    conflict = work / "conflict.sqlite"
    Assets(db=conflict).add(obspy.read_inventory(str(stations[3][4])), stations[0][0])
    record(
        cases,
        "share",
        "a version that differs stops the import",
        ["assets", "import", str(db), "--db", str(conflict)],
        1,
        ["differ from the versions here: nothing imported"],
    )
    cases[-1].detail = f"rows left: {len(Assets(db=conflict).list())}"

    # 8. eight adds at once to one UID: distinct versions
    parallel = work / "parallel.sqlite"
    sources = [str(path) for _, _, _, _, path in stations[:8]]
    with ThreadPoolExecutor(8) as pool:
        runs = list(
            pool.map(
                run_nrlx,
                [
                    ["assets", "add", source, "--uid", "RACE", "--db", str(parallel)]
                    for source in sources
                ],
            )
        )
    versions = sorted(row.version for row in Assets(db=parallel).list("RACE"))
    check(
        cases,
        "concurrency",
        "8 adds at once to one UID",
        all(code == 0 for code, _ in runs) and versions == list(range(1, 9)),
        f"exits {[code for code, _ in runs]}, versions {versions}",
    )

    # 9. errors and a newer layout
    record(
        cases,
        "errors",
        "--uid without --add-asset",
        ["response", "--sensor", picked_sensors[0], "--uid", "X", *common],
        1,
        ["--uid names the asset of --add-asset"],
    )
    record(
        cases,
        "errors",
        "--add-asset without station or uid",
        ["response", "--sensor", picked_sensors[0], "--add-asset", *common],
        1,
        ["needs --station or --uid"],
    )
    record(
        cases,
        "errors",
        "a UID that cannot name a folder",
        [
            "response",
            "--sensor",
            picked_sensors[0],
            "--add-asset",
            "--uid",
            "../x",
            *common,
        ],
        1,
        ["must be letters"],
    )
    record(
        cases,
        "errors",
        "get an unknown UID",
        ["assets", "get", "NOPE", "-o", str(work / "n.xml"), *on_db, *common],
        1,
        ["No asset NOPE"],
    )
    record(
        cases,
        "errors",
        "keys on the parts without a catalog",
        [
            "assets",
            "get",
            stations[0][0],
            "STS-2",
            "-o",
            str(work / "n.xml"),
            *on_db,
            "--cache-root",
            str(work / "empty_cache"),
        ],
        1,
        ["run nrlx sync"],
    )
    record(
        cases,
        "errors",
        "get to an unknown extension",
        ["assets", "get", stations[0][0], "-o", str(work / "n.txt"), *on_db, *common],
        1,
        ["Cannot tell the format from .txt"],
    )
    newer = work / "newer.sqlite"
    shutil.copy(db, newer)
    with sqlite3.connect(newer) as connection:
        connection.execute("PRAGMA user_version = 2")
    record(
        cases,
        "errors",
        "a database of a newer layout",
        ["assets", "list", "--db", str(newer)],
        1,
        ["of a newer nrlx"],
    )
    missing = work / "none.sqlite"
    record(
        cases,
        "errors",
        "list a missing database",
        ["assets", "list", "--db", str(missing)],
        0,
        ["No assets in"],
    )
    cases[-1].detail = f"created: {missing.exists()}"
    cases[-1].ok = cases[-1].ok and not missing.exists()

    # convert errors
    record(
        cases,
        "convert errors",
        "missing file",
        ["convert", str(work / "none.xml"), "-o", str(work / "a.resp")],
        1,
        ["Error:"],
    )
    record(
        cases,
        "convert errors",
        "unknown channel",
        ["convert", f"{stations[0][4]}#XY.A00.00.BHZ", "-o", str(work / "a.resp")],
        1,
        ["No channel XY.A00.00.BHZ"],
    )
    record(
        cases,
        "convert errors",
        "not a response file",
        ["convert", str(db), "-o", str(work / "a.resp")],
        1,
        ["Cannot read"],
    )

    result = AssetsResult(cases=cases, requests=requests, rows=assets.list())
    (arguments.out / "assets.json").write_bytes(
        msgspec.json.format(msgspec.json.encode(result), indent=1)
    )
    passed = sum(case.ok for case in cases)
    print(f"passed {passed} of {len(cases)}, requests {requests}")


if __name__ == "__main__":
    main()
