# End-to-end batteries

Scripts that run nrlx on random parts of the real NRL and check the results with
obspy and scipy, independently of the checks of nrlx itself. They give the numbers
of the validation of nrlx. They are not tests: pytest never runs them, and some of
them send requests to the public NRL service.

## Setup

In an environment with nrlx installed (its `nrlx` command beside the Python that
runs the scripts) and scipy, sync the catalog and the local copy of the NRL in a
cache folder:

```bash
pip install -e '.[dev]'
nrlx sync --cache-root CACHE
nrlx local sync --cache-root CACHE
```

## Scripts

Each takes `--cache-root CACHE --out OUT` and writes a JSON file in `OUT`. The
random parts come from `--seed`, so a run picks the same parts on the same NRL.

| Script | Service requests | Writes | What it checks |
|---|---|---|---|
| `build_battery.py` | about 80, spaced by `--pause` | `battery.json`, `pairs/` | 30 pairs and 20 single parts: the service build against the local one and against a sensor from its file; StationXML and RESP read back |
| `cli_battery.py` | about 10 | `cli.json`, `cli/` | `nrlx response` through the command: sources, formats, parts from files, `--split`, errors; `nrlx doctor` on each file. Needs `battery.json` |
| `convert_battery.py` | none | `convert.json`, `convert/` | `nrlx convert` on 46 instruments: StationXML, RESP, dataless SEED by obspy, SACPZ against evalresp and scipy |
| `assets_battery.py` | about 20 | `assets.json`, `assets/` | `nrlx assets` through the commands: adds, duplicates, variants, get, export and import, 8 concurrent adds, errors |
| `scan_nrl.py` | none | `scan.json` | every file of the local copy with the physical checks of `nrlx doctor` |

```bash
python scripts/e2e/build_battery.py --cache-root CACHE --out OUT
python scripts/e2e/cli_battery.py --cache-root CACHE --out OUT
python scripts/e2e/convert_battery.py --cache-root CACHE --out OUT
python scripts/e2e/assets_battery.py --cache-root CACHE --out OUT
python scripts/e2e/scan_nrl.py --cache-root CACHE --out OUT
```

A case that fails records its error in the JSON file and the battery goes on.
