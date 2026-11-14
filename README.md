# nrlx

[![PyPI](https://img.shields.io/pypi/v/nrlx)](https://pypi.org/project/nrlx/)
[![Python versions](https://img.shields.io/pypi/pyversions/nrlx)](https://pypi.org/project/nrlx/)
[![CI](https://github.com/vishnurajsreerajnair/nrlx/actions/workflows/ci.yml/badge.svg)](https://github.com/vishnurajsreerajnair/nrlx/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**NRL eXtended** — a Python CLI and library for browsing EarthScope/IRIS's Nominal
Response Library (NRL v2) and building seismic instrument responses.

## Quickstart

How it works, in short: `nrlx` keeps one local copy of IRIS's NRL catalog on your
disk, you describe your instrument with a few keys, and `nrlx` asks IRIS to build
the actual response. One command finds and writes:

```bash
pip install nrlx

nrlx sync                                   # download the catalog and its code table (first run and refreshes)

nrlx response --sensor luni,tellus          # what matches, and what still varies
nrlx response --sensor luni,tellus,LP=1 \
  --datalogger centaur,FR=100,FV=40Vpp,DF=Off,FP=Linear \
  --network XY --station TST --location 00 --channels HHZ,HHN,HHE \
  -o station.xml                            # a real StationXML file

nrlx doctor station.xml                     # sanity-check what you wrote
```

Without `-o`, `nrlx response` only shows: the matches of each part and the
parameters that still vary between them. Add keys until each part matches one
configuration, then add `-o FILE`. Not sure where to start? `nrlx response -i`
asks the parts step by step, writes the file and prints the same command line.

That `station.xml` is a real FDSN StationXML file built by IRIS's own service:
load it anywhere that reads StationXML, including
`obspy.read_inventory("station.xml")`.

## Install

```bash
pip install nrlx
```

nrlx needs Python 3.11 or later, and installs `obspy` with it: the responses it
builds are obspy objects in memory (see [Python library](#python-library)).

## Concepts

- **Catalog**: IRIS's tree of every nominal response, organized as `element`
  (sensor, datalogger, integrated, soh) → `manufacturer` → `model` →
  `configuration`.
- **instconfig**: the exact identifier of one configuration, e.g.
  `sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel`. Its parts after the
  model are two-letter codes and values (`SG1500` is a sensitivity of 1500 V/m/s);
  `nrlx prefixes` decodes them. It is what nrlx sends to IRIS; the keys exist to
  find it.
- **Local cache**: nrlx keeps one copy of the catalog and of its code table on
  disk (under your platform cache dir), so finding is instant and offline. `nrlx
  sync` refreshes both.

## Commands

| Command | What it does |
| --- | --- |
| `nrlx status [--live]` | Show version and local cache info; `--live` also checks the service. |
| `nrlx sync` | Download the current NRL catalog and code table into the local cache. |
| `nrlx prefixes [query]` | Decode the two-letter parameter codes of the instconfigs (LP, FR, FV, ...). |
| `nrlx response` | Find configurations by keys, and write their response (StationXML, RESP or SACPZ). |
| `nrlx convert <file> -o <out>` | Convert a response file to StationXML, RESP or SACPZ, read back and checked. |
| `nrlx local sync\|status\|remove` | Keep a local copy of the whole NRL, for `nrlx response --source local`. |
| `nrlx doctor <file>` | Run structural health checks on a saved response file. |

Run `nrlx <command> --help` for the full option list.

### Finding: keys

`nrlx response` without arguments shows the catalog: each manufacturer of each
element with its counts. Bare keys (`nrlx response sts-2`, `--element sensor` to
narrow) explore every element; the parts `--sensor`, `--datalogger`,
`--integrated` and `--soh` are what `-o` writes. A sensor, a datalogger or both;
an integrated instrument or a state of health channel alone.

The keys of a part are comma-separated or repeated, in any order. Each is:

- a **word**: a manufacturer (`luni`), a model, a part of the instconfig (`LP1`,
  `Q330HR_PG1`), a parameter value (`'400 V/m/s'`), or the exact instconfig. A
  whole name or part wins over the start of one, which wins over a text found
  inside: `LP1` keeps the LP1 configuration, not LP10 and LP120. A note says when
  a word matched only the start of a name or inside a text;
- a **condition** `name<op>value` with `=`, `<`, `>`, `<=`, `>=`, or a range
  `FR=100..500`, `FR=100..`, `FR=..200` (shell-safe, no quotes). The name is a
  code (`FR`, `LP`) or the start of a word of a parameter name (`corner>=60`);
  numbers are compared as numbers, so `FR=40` is 40 Hz, not 400 Hz.

What you see depends on how many configurations match: more than 20 are grouped
by model, with the parameters that still vary in each; up to 20 are listed one
per row; one is shown in full, with every parameter. When nothing matches, nrlx
says which key leaves no configuration, and suggests the nearest names or the
values there.

### Writing: channels, format, labels

```bash
nrlx response --sensor streckeisen,STS-2,EG3,SG=1500 \
  --datalogger Q330HR_PG1,FR=40,ADHR,LRbelow100 \
  --network XY --station MYSTN --location 00 --channels BHZ,BHN,BHE \
  --starttime 2021-01-01 \
  --latitude 49.096 --longitude 8.432 --elevation 112 \
  -o station.xml
```

- The format comes from the extension: `.xml` for StationXML, `.resp` for RESP,
  `.pz` for SACPZ; `--format stationxml|resp|sacpz` overrides it. The RESP writer
  keeps 16 significant digits.
- `--channels` are written as given, all in one file; `--split` writes one file
  per channel, named by its SEED id (`station_XY.MYSTN.00.BHZ.xml`). A channel
  code whose band letter does not fit the sample rate (SEED norm) gets a one-line
  note, never an error.
- The service builds the response once; nrlx copies it for each channel and sets
  the network, station, location, times (`--starttime`, `--endtime`, UTC) and the
  place (`--latitude`, `--longitude` in degrees; `--elevation` and `--depth` in
  metres, 0 unless given). The labels not given keep the service placeholders.
- A response nrlx does not combine itself (the service's, or a part alone from
  the local copy) is written as received, with a note when it contradicts itself:
  a normalization factor that does not give its stage's gain (12 % of the NRL
  sensors), or a stated sensitivity its stages do not give (more than 0.1 %).

### Your own sensor or datalogger

```bash
nrlx response --sensor-file my_sensor.xml#XX.SENS..HHZ \
  --datalogger centaur,FR=100,FV=40Vpp,DF=Off,FP=Linear \
  --network XY --station TST --channels HHZ -o station.xml
```

- `--sensor-file` and `--datalogger-file` take the part from any file obspy
  reads (StationXML, RESP, dataless SEED), in place of `--sensor` or
  `--datalogger`; `FILE#NET.STA.LOC.CHA` picks a channel of a file with several.
  The file can hold the part alone or a whole channel: the sensor is taken up to
  its voltage output, the datalogger from its voltage input.
- The other part comes from the NRL by keys as usual (or from a file too), and
  nrlx combines the two itself: it chains the units at the voltage, corrects the
  normalization factors that contradict their gains, and computes the overall
  sensitivity as obspy does. Notes say what was filled or corrected.
- `-i` asks the NRL parts only, so it does not take a file.

### Offline: the local NRL

```bash
nrlx local sync          # the whole NRL: about 300 MB to download, 2.8 GB on disk
nrlx response --sensor luni,tellus,LP=1 \
  --datalogger centaur,FR=100,FV=40Vpp,DF=Off,FP=Linear --source local -o st.xml
nrlx local status        # folder, files, size, date
nrlx local remove        # asks first (--yes to skip); the catalog stays
```

- `nrlx local sync` downloads the catalog, the code table and the zip of the
  whole NRL from the service, unzips it in the cache (`<cache>/nrl/NRL`, the
  layout of the zip, which obspy's NRL client also opens) and checks that every
  configuration of the catalog has its file. The three replace the previous ones
  together; a failure keeps the previous copy.
- `--source local` builds without any request: a part alone is its file, a
  sensor and a datalogger are combined by nrlx (as with `--sensor-file`). With
  `--source service` (the default) the service combines the NRL parts.

### Converting a file

```bash
nrlx convert station.dataless -o station.xml       # every channel, one file
nrlx convert station.xml -o station.resp --split   # one file per channel
nrlx convert "station.xml#XY.MYSTN.00.BHZ" -o bhz.pz
```

- The input is any file obspy reads: StationXML, RESP, dataless SEED, XSEED,
  SC3ML. The output is StationXML, RESP or SACPZ, from the extension (`.xml`,
  `.resp`, `.pz`) or `--format`.
- The file written is read back and compared with the input. StationXML and RESP
  must give the same curve (within 1e-9) or the command fails, keeping the file
  to look at.
- SACPZ keeps only the first poles and zeros stage and the overall sensitivity;
  a note says how far that is from the whole response (an STS-2 on a Q330 at
  40 sps: within 4.9 % up to 3.6 Hz, 28.9 % at 16 Hz). Channels SACPZ cannot hold
  (no poles and zeros, or an input other than m, m/s or m/s**2) are refused
  before writing, where obspy would skip them silently.

## Python library

Everything the CLI does is a thin layer over the `nrlx` package:

```python
from pathlib import Path

from nrlx import Nrlx, write_resp
from nrlx.io.inventory import read_part

nrl = Nrlx.from_cache()                      # the catalog and code table on disk
# nrl = Nrlx.sync()                          # or download fresh ones first

# Find: the rows carry their parents, with what still varies
found = nrl.find(["luni", "tellus"], "sensor")
for element, manufacturer, model, configuration in found.rows:
    print(model.name, configuration.instconfig, configuration.parameters)
print(found.varying)                         # {"Long-Period_Corner": ["1 s", ...], ...}

# Build: each part resolves to one configuration, then one request
inventory, notes = nrl.response(
    sensor=["luni", "tellus", "LP=1"],
    datalogger=["centaur", "FR=100", "FV=40Vpp", "DF=Off", "FP=Linear"],
    network="XY", station="TST", location="00", channels=["HHZ", "HHN", "HHE"],
    latitude=45.6, longitude=8.9,
)

# Your own sensor (any file obspy reads) with an NRL datalogger, combined by nrlx;
# the notes say what it filled or corrected
sensor = read_part(Path("my_sensor.xml"), "XX.SENS..HHZ")
inventory, notes = nrl.response(
    sensor_response=sensor,
    datalogger=["centaur", "FR=100", "FV=40Vpp", "DF=Off", "FP=Linear"],
    channels=["HHZ"],
)

inventory.write("station.xml", format="STATIONXML")   # an obspy Inventory
text = write_resp(inventory)                          # RESP, which obspy cannot write
```

nrlx raises built-in exceptions: `LookupError` when a part matches no
configuration or several (the message lists the hints or what still varies),
`ValueError` for an invalid request or catalog, `FileNotFoundError` when the
cache has not been synced, and `httpx.HTTPError` when the service cannot be
reached. Each part resolves before any request, so a wrong selection fails
offline.

## Status

Working end to end against the live NRL v2 service (released 0.2.x on PyPI; 0.1.0
was an early skeleton, yanked): finding by keys and conditions, sensor and
datalogger combination (also with your own sensor or datalogger files),
StationXML and RESP writing with any channel codes, and the structural `doctor`
check, and a local copy of the NRL to build offline. Planned next: format
conversion, deeper doctor checks and local sensor assets. See [CHANGELOG.md](CHANGELOG.md) for details.

## Note for developers

This is pre-1.0 and the public API (both CLI flags and the Python classes) can
still change between releases. The package is organized in layers, each
importing only the ones below it:

| Layer | Holds |
| --- | --- |
| `nrlx/schema/` | msgspec structs of every input: the NRL service JSON (`catalog`, `prefixes`), the cache files, and the request `response`, with its validation |
| `nrlx/models/` | the structs with their methods (`Catalog`, `Found`), plus `Nrlx` |
| `nrlx/core/` | pure functions on plain values: matching, SEED band codes, `/combine` parameters, the combination of responses, the amplitudes of the stages, the conversion checks, doctor checks |
| `nrlx/io/` | the NRL service (httpx), the local cache and the local NRL, obspy reading, labelling and writing, the RESP writer, the SACPZ reader |
| `nrlx/tools/cmd/` | the `nrlx` commands, the only code that prints and exits |

Library code raises built-in exceptions, and each command catches the ones it
can get. [CLAUDE.md](CLAUDE.md) lists the code conventions.

Not yet: `nrlx doctor` does not check SACPZ files, and nrlx does not read
SACPZ as an input (obspy cannot). Issues and PRs welcome.

## Disclaimer

This project is not affiliated with EarthScope, IRIS, or the official Nominal Response Library.
NRL data remains owned/maintained by its respective providers.
