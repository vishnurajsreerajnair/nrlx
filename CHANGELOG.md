# Changelog

## [Unreleased]

The package is restructured in layers, as in isamgeo-seismic-tools: `schema`
(msgspec structs of every input), `models` (the structs with their methods), `core`
(pure functions), `io` (service, cache, obspy) and `tools/cmd` (the commands, the
only place that prints and exits). `nrlx browse` and `nrlx build` become one
command, `nrlx response`; the Python API changes as listed below.

### Added

- **`nrlx response`**, the command finding and writing responses, in place of
  `nrlx browse` and `nrlx build`. Without keys it shows the catalog; bare keys
  (`--element` to narrow) explore every element; the parts `--sensor`,
  `--datalogger`, `--integrated` and `--soh` take keys, comma-separated or
  repeated. What matches is shown by how many: more than 20 grouped by model with
  the parameters that still vary (by code), up to 20 one per row, one in full with
  every parameter; notes on loose words, hints when nothing matches (exit 1). When
  every part matches one configuration it prints the command line with the
  instconfigs; with `-o FILE` it writes the response, `.xml` for StationXML or
  `.resp` for RESP (`--format` overrides), every channel in one file or one per
  channel with `--split` (`st_XY.TST.00.HHZ.xml`). `--channels` are written as
  given, with a note when a band code does not fit the sample rate (SEED norm,
  `core.seed.band_codes`). `-i` asks the parts (manufacturer, model, then each
  varying parameter, with the questions of the code table), the labels and the
  file, then prints the same command line and writes.
- `core.matching.varying_values`, the values of each parameter that differs
  between configurations.
- msgspec structs of the NRL service JSON: `schema.catalog` (the `/catalog` tree),
  `schema.cache.CatalogFileInput` (the catalog file) and `schema.prefixes` (the
  `/prefix-lookup` table). The catalog is decoded and validated in one step, and
  the structs accept unknown fields, so a field added by the service does not
  break nrlx.
- `schema.instrument.InstrumentInput` and `models.instrument.Instrument`, the
  selection of a sensor or datalogger (exact instconfig, or manufacturer, model and
  keys), and `schema.build.BuildInput` and `models.build.Build`, the request of
  `nrlx build`. The rules of a request are checked once, in the structs: an
  instconfig with filters, repeated channels, merging fewer than two channels or
  a format other than uncompressed StationXML.
- `nrlx -j`/`--version`, as in the other ISAMGEO tools.
- `nrlx status --live` shows the service version, from the `/version` endpoint
  (a few bytes, where the old check downloaded the whole catalog).
- `nrlx build` prints the resolved instconfig, to pin it with
  `--sensor-instconfig`/`--datalogger-instconfig`; `nrlx sync` prints the number
  of configurations.
- Tests split in `tests/lib` and `tests/entrypoints`, with the shared data in
  `tests/data` and a fake NRL service in `tests/conftest.py`. New tests for the
  obspy conversions and the StationXML merge, for the catalog validation and for
  the request rules. CI runs `ruff format --check` and Python 3.11 to 3.14.
- Coordinates of the station: `nrlx build --latitude --longitude` (with
  `--elevation` and `--depth` in metres, 0 by default) and the same fields of
  `BuildInput`. They are written on the station and on every channel of each
  StationXML (`io.inventory.set_coordinates`), merged or one per channel, instead
  of the service placeholders; they need the stationxml format, not zipped.
- **`Nrlx.response(...)`** returns an obspy `Inventory`: each part (`sensor`,
  `datalogger`, `integrated`, `soh`) selected by keys and resolved before any
  request, one `/combine` request, a copy of the channel for each code (written as
  given), and the network, station, location, times and coordinates set by nrlx
  (the labels not given keep the service placeholders). Its request is
  `schema.response.ResponseInput`, which checks the parts (a sensor, a datalogger
  or both, an integrated or a state of health channel alone), the channels, the
  times and the coordinates. `Nrlx.find(keys, element)` is `Catalog.find` with the
  code table. `io.inventory.label_channels` labels the channels, and
  `set_coordinates` works on an `Inventory`.
- `black --check` in the `dev` extra and in CI.
- **RESP writer**, `io.resp.write_resp(inventory)`: the responses of an obspy
  `Inventory` as RESP text, every channel one after the other, which obspy cannot
  write. Every stage type: poles and zeros (B053), coefficients (B054), response
  list (B055), FIR (B061) and polynomial (B062), each with its decimation (B057)
  and gain (B058), then the sensitivity (stage 0, B058) or the polynomial of the
  channel. The numbers keep 16 significant digits, so a float is written and read
  back exactly (the NRL service writes 6). Tested against three NRL
  configurations saved in `tests/data` (STS-2 + Q330HR, Tellus + Centaur, a
  polynomial sensor): read back by obspy, the curves equal those of the
  StationXML.
- Matching of the keys in `core.matching`, the base of the coming `nrlx response`:
  `split_condition` reads a condition on a parameter (`FR=40`, `corner>=60`, the
  range `FR=100..500`), `compare` compares a parameter value with it, as numbers
  when both are (`FR=40` is "40 Hz", not "400 Hz"), and `word_tier` finds a word
  as a whole part of the instconfig or a whole name, else at the start of one, else
  anywhere.

### Changed

- **`nrlx sync` also saves the code table** of the instconfig parameters (the
  `/prefix-lookup` endpoint) beside the catalog, `nrl/prefixes.json`; both are
  validated before either is written, so a broken download keeps the previous
  pair. `nrlx prefixes` reads it offline, with `--cache-root` instead of
  `--base-url`, and `Nrlx` holds it in `prefixes` (`Nrlx.from_cache` reads it,
  `Nrlx.sync` downloads it). A cache synced before this version has no table:
  run `nrlx sync` once.
- **`Catalog.find(keys, prefixes, element_name)`** returns a `Found`: the
  matching rows, the parameters that still vary between them (`varying`), notes on
  the words found only at the start of a name or inside a text, and hints when
  nothing matches (the key that leaves no row, the nearest names, the values of a
  parameter there). The words keep the rows with the lowest total tier, so their
  order does not matter; a condition names its parameter by code or by the start
  of a word of its name, among the parameters the other keys leave (`corner`
  alone may be Long-Period_Corner or High-Frequency_Corner). `Catalog.resolve`
  takes the keys and the code table and is built on it; its error lists what
  still varies. `get_configurations` keeps only the element filter: the
  manufacturer, model, instconfig and keys filters are keys of `find`;
  `contains_keys` is removed.
- mypy checks with `python_version = "3.12"`, as the numpy stubs need: with 3.11
  `mypy --strict` stopped on them before checking nrlx.
- **obspy and msgspec are required**, and Python 3.11 or later: the `nrlx[obspy]`
  extra and the lazy obspy import are removed.
- **The custom exceptions are removed** (`nrlx.exceptions`): nrlx raises
  built-in exceptions, caught in the commands. A missing catalog is a
  `FileNotFoundError`, an invalid catalog or request a `ValueError`, a selection
  matching no configuration or several a `LookupError`, a service error an
  `httpx.HTTPError`, a file error an `OSError`.
- **Removed, replaced by `Nrlx.response`**: `Nrlx.combine`, `BuiltResponse`,
  `BuildInput`/`Build`, `InstrumentInput`/`Instrument` and
  `io.inventory.merge_stationxml`. `combine_params` asks only the StationXML
  response, without the labels, and `cascade_instconfig` takes the list of the
  instconfigs of the parts. `from nrlx import Nrlx, Catalog, Found, write_resp`.
- Modules moved: `nrlx.nrl.Nrlx` to `nrlx.models.nrlx`, `BuiltResponse` to
  `nrlx.models.response`, `Catalog` to `nrlx.models.catalog`, the HTTP client to
  `nrlx.io.service` (functions `get_url` and `get` instead of `NRLClient`), the
  cache to `nrlx.io.cache`, the obspy conversions to `nrlx.io.inventory`, the
  doctor checks to `nrlx.core.doctor` and the CLI to `nrlx.tools.cmd` (the
  `nrlx` entry point is `nrlx.tools.cmd:app`). `from nrlx import Nrlx,
  BuiltResponse, Catalog, ResponseFormat` keeps working.
- `ResponseFormat` is a `Literal["resp", "stationxml", "stationxml-resp"]`
  instead of an enum: pass `format="resp"` instead of `ResponseFormat.RESP`.
- `Catalog` is the decoded JSON tree: `get_elements`, `get_manufacturers`,
  `get_models` and `get_configurations` return the nodes with their parents, for
  example `(element, manufacturer, model, configuration)`, and `resolve` returns
  the single matching configuration. `Catalog.search(query)` is
  `get_configurations(keys=[query])`, `Catalog.configuration(instconfig)` and the
  count properties are removed, `format_version` is a number (1.0), as in the
  service JSON.
- `Nrlx.resolve`, `resolve_sensor` and `resolve_datalogger` are
  `Nrlx.catalog.resolve("sensor", ...)`; `Nrlx` holds `catalog`, `base_url` and
  `timeout` instead of an `NRLClient`.
- The doctor checks are functions, `check_response(content, format)` returning
  `(severity, message)` pairs, instead of `HealthReport.from_file`.
- **Removed, replaced by `nrlx response`**: `nrlx browse` (summary, elements,
  manufacturers, models, configs, show) and `nrlx build`, with its
  `--sensor-instconfig`/`--sensor-keys` style flags, `--merge-channels` (one file
  with every channel is now the default, `--split` the other way) and `--zip`.
- The errors are printed on stderr.

### Fixed

- A code of the table (`FR`) stands for its parameter only: where the configurations
  searched do not have it, the condition matches none and the hint says so, instead
  of falling back to the start of a word (`--sensor FR=100` filtered the sensors by
  their High-Frequency corner).
- A condition with a number names one parameter more often: among the parameters
  its name stands for, those without a number in their values are left out
  (`sens>1000` is Sensitivity, not Sensor_Type). `resolve_parameter` takes the
  value of the condition and the values of the parameters.
- `nrlx response -i`: the prompts say `Choice (1-80)` instead of listing every
  number, a step with one option is taken without asking, and the channel prompt
  explains its empty default. The catalog view leaves out the manufacturers
  without models, which the NRL catalog lists.
- `nrlx sync` and `Nrlx.sync` validate the download before writing it: an error
  page or a broken catalog no longer replaces the previous catalog in the cache.
- Repeated channels are rejected, instead of writing the same file twice.
- File paths and catalog texts with square brackets are no longer read as Rich
  markup in the output.

## [0.2.1] - 2026-09-27

### Fixed

- Change of default base name.

## [0.2.0] - 2026-07-12

First functional release — working end to end against the live NRL v2 service.
(The `0.1.0` on PyPI was an early skeleton, now yanked; see below.)

### Added

- Typed `Catalog`/`Element`/`Manufacturer`/`Model`/`Configuration` library
  (`nrlx.catalog`), parsed once from the real IRIS NRL v2 `/catalog` endpoint.
- `nrlx.Nrlx` — the flagship class: resolves catalog selections to
  `instconfig` strings and builds real responses via the live `/combine`
  endpoint (RESP, StationXML, StationXML-Response, all confirmed to
  round-trip through `obspy.read_inventory()`).
- `Nrlx.from_cache()` / `Nrlx.sync()` constructors: use the catalog already on
  disk, or download a fresh one first and return a ready `Nrlx`.
- `Nrlx.combine()` returning a `BuiltResponse` held in memory, with
  `.save()`, `.to_inventory()`, `.to_response()`, and `.to_paz()` converters
  (the obspy-backed ones need the `nrlx[obspy]` extra).
- ObsPy-v1-style key selection: `resolve(keys=[...])` and repeatable
  `--sensor-key`/`--datalogger-key` CLI flags — unordered, case-insensitive
  substrings ANDed across manufacturer, model, instconfig, description, and
  parameter names and values (so `--sensor-key Sensitivity`, `--sensor-key
  40Vpp`, or `--sensor-key groundVel` all work).
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
  `elements`, `manufacturers`, `models`, `configs`, `show`), `build`, `doctor`.
- `nrlx browse show <instconfig>` prints one configuration in full — its
  description and every parameter (Sensitivity, Sensor_Type, corner period,
  ...) — so you can see which values are available as build keys.
- Free-text catalog search: `Catalog.search()` and the positional query on
  `browse manufacturers`/`models`/`configs` match manufacturer, model,
  instconfig, description, and parameter names/values, so `browse configs
  groundVel` finds configs by their physical parameters, not just their names.
- `Catalog.configuration(instconfig)` — exact instconfig lookup returning a
  single `Configuration` (or `None`).
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

## [0.1.0] - 2026-04-30

- Initial package skeleton, published to PyPI. Superseded by 0.2.0 and yanked:
  it predates the current architecture (a hard `obspy` dependency, no live
  NRL v2 client) and should not be installed.
