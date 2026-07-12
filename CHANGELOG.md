# Changelog

Newest first.

## [0.1.0] - 2026-07-12

First release.

### Added

- Typed `Catalog`/`Element`/`Manufacturer`/`Model`/`Configuration` library
  (`nrlx.catalog`), parsed once from the real IRIS NRL v2 `/catalog` endpoint.
- `nrlx.Nrlx` — the flagship class: resolves catalog selections to
  `instconfig` strings and builds real responses via the live `/combine`
  endpoint (RESP, StationXML, StationXML-Response, all confirmed to
  round-trip through `obspy.read_inventory()`).
- `Nrlx.combine()` returning a `BuiltResponse` held in memory, with
  `.save()`, `.to_inventory()`, `.to_response()`, and `.to_paz()` converters
  (the obspy-backed ones need the `nrlx[obspy]` extra).
- ObsPy-v1-style key selection: `resolve(keys=[...])` and repeatable
  `--sensor-key`/`--datalogger-key` CLI flags — unordered, case-insensitive
  substrings ANDed across manufacturer, model, instconfig, description, and
  parameter values (so `--sensor-key 40Vpp` or `--sensor-key "100 Hz"` work).
- `--channels` on `nrlx build`: several channels write one file each
  (`out_EHZ.xml`, ...), or one merged StationXML inventory with
  `--merge-channels` (needs the obspy extra).
- `nrlx prefixes [query]` decodes the two-letter instconfig parameter
  codes (LP, FR, FV, ...) via the NRL service's `/prefix-lookup` endpoint.
- Ambiguous-selection errors list candidate instconfigs one per line
  instead of a comma-separated wall.
- List-valued build flags take comma-separated values in one flag
  (`--sensor-keys a,b,c`, `--channels EHZ,EHN,EHE`); the singular repeated
  spelling (`--sensor-key a --sensor-key b`) remains as an alias.
- `nrlx.inventory` module: in-memory StationXML→Inventory/Response
  conversion and multi-channel merging, obspy imported lazily.
- Root-level exports: `from nrlx import Nrlx, BuiltResponse, Catalog,
  ResponseFormat`.
- `nrlx.doctor` — structural health checks on a saved response file (valid
  XML/RESP, expected elements/blockettes present), no `obspy` required.
- CLI commands: `status [--live]`, `sync`, `browse` (subcommands `summary`,
  `elements`, `manufacturers`, `models`, `configs`), `build`, `doctor`.
- Free-text positional search on `browse manufacturers`/`models`/`configs`
  (e.g. `nrlx browse configs lunitek`); `configs` additionally ORs the query
  across manufacturer, model, and instconfig via `Catalog.search()`.
- `--instconfig` filter on `browse configs`.
- CLI-level test suite (`tests/test_cli.py`) and a GitHub Actions CI workflow
  running ruff, mypy, and pytest on Python 3.10–3.13.
- `nrlx.formats` module holding `ResponseFormat` (re-exported from `nrlx.nrl`),
  so importing the offline `nrlx.doctor` no longer pulls in the network stack.
- `py.typed` marker (PEP 561), so downstream type checkers see nrlx's
  annotations.
- `__version__` read from package metadata — pyproject.toml is the single
  source of truth.

### Changed

- The flagship class is `Nrlx` (was `NRL`); `get_response()`/`save_response()`
  were removed in favor of `combine()` + `BuiltResponse`.
- `browse` restructured from one command with a string category argument
  into real subcommands, each exposing only the filters that apply to it.
- `init-cache`/`update-cache`/`info`/`ping` consolidated into `sync` and
  `status --live`.
- `nrlx response` renamed to `nrlx build`.
- `CacheInfo` moved from the removed `nrlx.models` into `nrlx.cache`.
- Exceptions renamed from the all-caps `NRLX*` family to `Nrlx*`
  (`NrlxError`, `NrlxCacheError`, `NrlxNetworkError`, `NrlxResponseError`).
- Single-class helpers moved to staticmethods on their owning class
  (`NRLClient._normalize_base_url`, `Nrlx._combine_params`,
  `HealthReport._check_resp`/`_check_xml_response`).

### Fixed

- `httpx` was used by `nrlx.client` but missing from packaged dependencies.
- A failed local file write during download was raised as `NrlxNetworkError`;
  it is now the base `NrlxError`, since the fetch had already succeeded.
- Removed the unused `NRLClient.get_text` method.
- `browse` silently ignored `--manufacturer`/`--model` filters on categories
  that didn't wire them up (now either applied correctly or rejected with a
  clear error, and now structurally impossible via typed subcommands).
- Dead code in a cache-file-resolution helper that returned the same value
  regardless of an existence check.
- Stale build artifacts (`dist/*.whl`, `dist/*.tar.gz`) removed from version
  control; `.gitignore` expanded.
- "Catalog file not found" error pointed at the removed `update-cache`
  command; it now says `nrlx sync`.

## Project inception - 2026-04-30

- Initial package skeleton (unversioned, never published).
