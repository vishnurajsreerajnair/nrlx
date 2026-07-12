# nrlx

**NRL eXtended** — a Python CLI and library for browsing EarthScope/IRIS's Nominal
Response Library (NRL v2) and building seismic instrument responses.

## Quickstart

How it works, in short: `nrlx` keeps one local copy of IRIS's NRL catalog on your
disk, you describe your instrument, and `nrlx` asks IRIS to build the actual
response file. Three commands:

```bash
pip install nrlx

nrlx sync                                 # download the catalog (first run and refreshes); always healthy to refresh the catalog!

nrlx build --sensor-keys streckeisen,STS-2,EG3,SG1500 \
  --output station.xml                    # a real StationXML/inv file

nrlx doctor station.xml                   # sanity-check what you built
```

Each comma-separated key in `--sensor-keys` is a word that must match somewhere
in the sensor's catalog entry. Too few keys? `build` lists every matching
configuration so you can add one more. Don't know the instrument names yet?
Explore first:

```bash
nrlx browse manufacturers streckeisen              # find a manufacturer by name
nrlx browse models --manufacturer streckeisen      # its models
nrlx browse configs streckeisen --element sensor   # exact configs + instconfigs
```

That `station.xml` is a real FDSN StationXML file straight from IRIS's own service - load it anywhere that reads StationXML, including `obspy.read_inventory("station.xml")`.

Full command reference and the ifs-and-buts (dataloggers, multiple channels, output formats) are below; a fuller walkthrough is planned for the project wiki.

## Install

```bash
pip install nrlx
```

Add `nrlx[obspy]` if you also want `obspy` available for downstream parsing of the
responses `nrlx` builds — `nrlx` itself never requires it.

## Concepts

Three terms cover everything nrlx does:

- **Catalog** -> IRIS's tree of every nominal response, organized as
  `element` (sensor / datalogger) → `manufacturer` → `model` → `configuration`.
- **instconfig** -> the exact identifier of one configuration, e.g.
  `sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel`. It is what `build`
  actually sends to IRIS. `browse` exists to help you find the right one.
- **Local cache** -> nrlx keeps one copy of the catalog on disk (under your
  platform cache dir) so browsing is instant and offline. `sync` refreshes it.

## Commands

| Command | What it does |
| --- | --- |
| `nrlx status [--live]` | Show version and local cache info; `--live` also checks connectivity. |
| `nrlx sync` | Download the current NRL catalog into the local cache. |
| `nrlx browse <summary\|elements\|manufacturers\|models\|configs\|show>` | Browse the cached catalog; `show <instconfig>` prints one config's full parameters. |
| `nrlx prefixes [query]` | Decode the two-letter parameter codes used in instconfigs (LP, FR, FV, ...). |
| `nrlx build` | Build a sensor(+datalogger) response and save it to a file. |
| `nrlx doctor <file>` | Run structural health checks on a saved response file. |

Run `nrlx <command> --help` for the full option list on any of these — each
`browse` subcommand only exposes the filters that actually apply to it.

`browse manufacturers`/`models` take an optional positional query that matches
*that level's own name* (a manufacturer name, a model name) - `--element`/
`--manufacturer` remain as flags to narrow by a parent level. `browse configs`
is the exception: its positional query matches manufacturer, model, *and*
instconfig at once, since a config doesn't have a single "own name." So
`browse models streckeisen` looks for a model literally named "streckeisen"
(nothing) - use `browse models --manufacturer streckeisen` instead - while
`browse configs streckeisen` works directly, because configs search all three
fields - plus each config's description and parameter names/values, so
`browse configs groundVel` or `browse configs "400 V/m/s"` find configs by their
physical parameters, not just their names.

The list views stay deliberately narrow. To see everything one configuration
carries - description and every parameter (Sensitivity, Sensor_Type, corner
period, ...) - use `browse show`:

```bash
nrlx browse show sensor_Lunitek_TELLUS_LP1_SG400_STgroundVel
```

Those parameter values are exactly what you can pass as build keys (next section).

If a sensor/datalogger filter in `nrlx build` matches more than one configuration,
it lists every matching `instconfig` string so you can pin down the exact one with
`--sensor-instconfig`/`--datalogger-instconfig` instead.

### Selecting by keys instead of instconfig

Instead of hunting down the exact instconfig, describe the instrument with
comma-separated `--sensor-keys`/`--datalogger-keys` (ObsPy-v1 style). Every key
must match somewhere in a configuration - manufacturer, model, instconfig,
description, or a parameter name or value like `Sensitivity`, `40Vpp`, or
`groundVel` (quote keys with spaces: `--sensor-keys 'STS-2,100 Hz'`). Use
`nrlx browse show <instconfig>` to see the full parameter list you can key on.
If the selection is ambiguous, nrlx lists the matching instconfigs; pick distinguishing fragments from that list as your next keys:

```bash
nrlx build \
  --sensor-keys streckeisen,STS-2,EG3,SG1500 \
  --datalogger-keys Q330HR_PG1,FR40,ADHR,LRbelow100 \
  --output station.xml
```

The singular repeated form also works (`--sensor-key streckeisen --sensor-key
STS-2 ...`), and both spellings accept either style.

Candidate instconfigs are full of coded fragments like `LP120`, `FR500`, or
`FV10Vpp`. Run `nrlx prefixes` (or `nrlx prefixes corner` to filter) to decode
them — it fetches the official code table from the NRL service, e.g.
LP = Long-Period Corner, FR = Final Sample Rate, FV = Full-Scale Voltage.

### Multiple channels

`--channels` takes comma-separated channel codes. Several channels write one
file per channel (`station_EHZ.xml`, `station_EHN.xml`, ...); add `--merge-channels` to
get one StationXML inventory containing all of them (needs
`pip install 'nrlx[obspy]'`):

```bash
nrlx build \
  --sensor-keys streckeisen,STS-2,EG3,SG1500 \
  --network XY --station MYSTN \
  --channels EHZ,EHN,EHE --merge-channels --output station.xml
```

## Python library

Everything the CLI does is a thin layer over the `nrlx` package:

```python
from nrlx import Nrlx, ResponseFormat

nrl = Nrlx.from_cache()                      # loads the catalog already on disk
# nrl = Nrlx.sync()                          # or download a fresh one first
#                                            # (first run / to refresh)

# Find and browse
nrl.catalog.search("lunitek")                # free-text across the catalog
nrl.catalog.configurations(element="sensor", manufacturer="Streckeisen")

# Combine sensor + datalogger, entirely in memory (nothing written to disk)
built = nrl.combine(
    sensor_keys=["streckeisen", "STS-2", "EG3", "SG1500"],
    datalogger_keys=["Q330HR_PG1", "FR40", "ADHR", "LRbelow100"],
)

built.content          # raw StationXML bytes
built.save("out.xml")  # write a file only when you want one
```

Each element can be selected by keys (resolved through the catalog) *or* by an
exact instconfig string - and you can mix the two. The datalogger is optional;
omit it for a sensor-only response.

```python
built = nrl.combine(
    sensor_instconfig="sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel",
    datalogger_keys=["Q330HR_PG1", "FR40"],   # or datalogger_instconfig="..."
)
```

Passing both `sensor_keys` and `sensor_instconfig` for the same element is an
error (same for the datalogger) - give exactly one.

`combine()` also takes the StationXML identity and validity fields — pass them
and IRIS stamps them into the response instead of placeholders:

```python
built = nrl.combine(
    sensor_keys=["streckeisen", "STS-2", "EG3", "SG1500"],
    network="XY", station="MYSTN", location="00", channel="HHZ",
    starttime="2021-01-01", endtime="2025-01-01",
)
```

All six are optional; omit them and the service fills in placeholders. If you'd
rather not commit to StationXML naming at all, skip them and take the bare
`Response` instead (below).

With the `nrlx[obspy]` extra installed, a `BuiltResponse` converts in memory —
this is the NRL-v1-style workflow, and the way around StationXML's strict
network/station/channel naming: take the bare `Response` and attach it to
channels you build yourself, with whatever codes you need.

```python
inv  = built.to_inventory()   # obspy Inventory
resp = built.to_response()    # bare obspy Response - no naming attached
paz  = built.to_paz()         # poles & zeros stage

from obspy.core.inventory import Channel
channel = Channel(code="HHZ", location_code="00",
                  latitude=..., longitude=..., elevation=..., depth=...,
                  response=resp)             # your naming, your inventory
```

## Status

v0.1.0 - the first release, working end to end against the live NRL v2 service:
catalog browsing, key/instconfig selection, sensor+datalogger combination,
multi-channel builds with optional merging, in-memory obspy conversion, and the
structural `doctor` check. Planned next: response format merging and conversion
(dataless SEED, RESP, SAC PZ), a suggestion engine, a TUI, a web interface, and
local sensor-asset management. See [CHANGELOG.md](CHANGELOG.md) for details.

## Note for developers

This is pre-1.0 and the public API (both CLI flags and the Python classes in
`nrlx.catalog`/`nrlx.nrl`) can still change between releases. The code favors small,
immutable dataclasses with explicit constructors (`Catalog.from_file`,
`Nrlx.from_cache`) over free functions passing raw dicts around — if you're
extending it, follow that pattern rather than introducing a parallel one.

Deliberately out of scope for now: combining a response file you already have
(e.g. a manufacturer RESP) with an NRL entry — nrlx v0.1 is strictly "NRL in,
NRL out." Merging and converting arbitrary response sources (dataless SEED,
RESP, SAC PZ) is the planned `nrlx.response` phase. Issues and PRs welcome.

## Disclaimer

This project is not affiliated with EarthScope, IRIS, or the official Nominal Response Library.
NRL data remains owned/maintained by its respective providers.
