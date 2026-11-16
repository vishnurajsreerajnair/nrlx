# Changelog

## [Unreleased]

## [0.3.0b1] - 2026-11-16

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
  instconfigs; with `-o FILE` it writes the response, `.xml` for StationXML,
  `.resp` for RESP or `.pz` for SACPZ (`--format` overrides), every channel in one file or one per
  channel with `--split` (`st_XY.TST.00.HHZ.xml`). `--channels` are written as
  given, with a note when a band code does not fit the sample rate (SEED norm,
  `core.seed.band_codes`). `-i` asks the parts (manufacturer, model, then each
  varying parameter, with the questions of the code table), the labels and the
  file, then prints the same command line and writes. `--sensor-file` and
  `--datalogger-file` take a part from a file obspy reads (`FILE#NET.STA.LOC.CHA`
  for one of its channels), combined by nrlx with the other part, by keys or from
  a file; each file part is shown with its stages and units, and the printed
  command line keeps the file options. The rules of the parts, the labels, the
  times and the place (`ResponseInput`) are checked before any table, so a wrong
  request fails before suggesting `-o FILE`; `-i` refuses the file options.
- **`nrlx convert IN -o OUT`**, conversion of a response file obspy reads
  (StationXML, RESP, dataless SEED, XSEED, SC3ML) to StationXML, RESP or SACPZ,
  the format from the extension (`.xml`, `.resp`, `.pz` or `.sacpz`; `--format`
  overrides), every channel in one file or one per channel with `--split`,
  `IN#NET.STA.LOC.CHA` for one channel. The file written is read back and
  compared with the input (`io.inventory.verify_written`): StationXML and RESP
  must give the same curve within 1e-9 at 60 frequencies up to 0.4 of the rate
  (the same coefficients for a polynomial), or the command fails and keeps the
  file to look at. SACPZ keeps the first poles and zeros stage and the overall
  sensitivity: a note says how many stages it drops and how far it is from the
  whole response, in band and at the top (an STS-2 on a Q330 at 40 sps: within
  4.9 % up to 3.6 Hz, 28.9 % at 16 Hz). SACPZ leaves out, with a note, the
  channels obspy would skip silently: without poles and zeros, or with an input
  other than m, m/s or m/s**2 (a pressure sensor, a polynomial).
  `nrlx response -o FILE.pz` writes SACPZ too.
  `io.inventory.read_channels(path, seed_id)` reads every channel of a file or
  those of a SEED id (merging the stations obspy splits when it reads a RESP of
  several channels, so a RESP converts to one station with all its channels), `write_inventory(inventory, path, format)` writes the three
  formats, `io.sacpz.read_sacpz(text)` reads SACPZ (which obspy writes but does
  not read: SEED id, zeros, poles, constant, and the rate of its `* SAMPLE RATE`
  comment or None), and `core.convert` has `output_format` and the amplitudes of the
  check (`pz_amplitude`, `relative_difference`, `check_frequencies`). The tests
  make their dataless SEED at run time, from the RESP of `tests/data`, with
  obspy's `Parser.write_seed`.
- **Assets**, `nrlx assets add|list|get|deprecate|delete|export|import`: the
  responses you build or calibrate, kept as the StationXML file as built, under
  a UID (the station code by default, `--uid` for another), in a SQLite database
  (`assets.sqlite` in the cache, `--db` for another). `nrlx response
  --add-asset` stores what it builds, with or without `-o`; the UID is checked
  before any request, and a response the UID already has gives a note instead of
  a new version (`nrlx assets add` refuses it). The versions of a UID are one
  sequence; each keeps the variant of its channels (sample rate, input units,
  sensitivity, and the NRL instconfigs of the sensor and the datalogger), which
  must share one response. `get UID [KEYS] -o FILE` writes the latest version in
  use that the keys pick: the keys of `nrlx response` on the NRL parts (`STS-2`,
  `FR=40`) and `rate=`, `units=` on the file; several variants left are listed,
  `--version N` takes any version. The file is written in any of the three
  formats and read back, as by `nrlx convert`. `deprecate --version N` stops a
  version from being picked (`--undo` puts it back); `delete` asks first (`--yes`).
  `export DIR` writes `UID/vN.xml` with a `manifest.json` of the rows (and their
  SHA-256); `import` merges an export or another database, skipping the versions
  already here and refusing, before writing anything, one that differs or a file
  changed since the export. A database of a newer layout (`PRAGMA user_version`)
  is refused. Python: `Nrlx.assets` (`add`, `select`, `get`, `list`,
  `deprecate`, `delete`, `export_to`, `import_from`) on `Nrlx.from_cache(...,
  assets_db=...)`; `models.assets.Assets`, `io.assets`, `core.assets`,
  `schema.asset.AssetRow`.
- **Provenance comment**: `Nrlx.response` (and so `nrlx response`) writes on each
  channel a StationXML comment of subject `nrlx` with the instconfigs it was built
  from and their source, `built by nrlx 0.2.1 (service): sensor=... datalogger=...`
  (`file` for a part from a file; `core.assets.read_source` reads the source), so that a file added later as an asset keeps its NRL keys. RESP and
  SACPZ have no comments and leave it out. `io.inventory.set_provenance`,
  `stationxml_text`, and `response_difference` (the read-back comparison of
  `verify_written`, also used by the assets).
- **Notes on the responses kept as received**, `core.combine.received_notes`:
  the responses nrlx does not combine itself (the service's, and a part alone
  from the local copy) are written as the NRL gives them, and `Nrlx.response`
  returns a note for each poles and zeros stage whose normalization factor does
  not give its gain at its normalization frequency (more than 0.1 %), and when the
  stated sensitivity differs from the one of the stages by more than 0.1 %
  (`SENSITIVITY_NOTED`; for example an HG-7 on a GaiaCode TAU at 8 sps, stated
  x3.64 what its stages give). The command prints them as the other notes.
  These rules are in `normalization_values`, `stated_ratio`, `sensor_frequency`
  and `band_fraction`, which the doctor checks share.
- **Physical checks of a channel** (doctor tier 2), in `core.doctor`, each a list
  of `(severity, message)` with the new severity `info` for a check that does not
  apply:
  - `check_amplitude`: the stated sensitivity against its stages by evalresp's
    rules (error beyond 1 %), a missing or non-positive sensitivity (error), and
    warnings for a normalization factor that does not give its gain, a sensitivity
    at or above Nyquist or out of the sensor's flat band, and a FIR whose
    coefficients do not sum to 1.
  - `check_chains`: errors for stages not numbered 1 to N, a break in the units,
    a last stage not in counts, a sensitivity in other units than the stages, a
    digital stage without decimation, and decimations ending at another rate than
    the channel's. A break in the rate chain is a warning: evalresp takes each
    stage at its own rate.
  - `check_poles` / `check_poles_zeros`: errors for unstable poles (analog with a
    positive real part, digital outside the unit circle), and a warning for a zero
    on a pole. `check_sacpz` adds the CONSTANT.
  - `check_codes`: warnings for a band code that does not fit the sample rate and
    an instrument code that does not fit the input units (H, L, P in m/s, N in
    m/s**2, D in Pa).
  - `check_channel(response, sample_rate, code)` runs the four groups and returns
    flat `(group, severity, message)` findings, without the codes when `code` is
    None (a part of the NRL); `nrlx doctor` and `scan_nrl` both use it.

  On the whole NRL v2 they find 18 sensor files with poles of the wrong sign
  (REFTEK RT131, RSensors CME, Guralp CMG-5T, ...), 448 datalogger files with an
  analog DC filter typed as a Z transform (DTCC, MagseisFairfield), 96 with the
  reverse (SeismicSource DAQ3), and 1,459 whose rates do not chain.
- **A channel against its NRL nominal** (doctor tier 3). `Nrlx.nominal(channel,
  sensor=, datalogger=, integrated=, source=)` builds the nominal of the parts
  given, else of the instconfigs of the provenance comment, from the comment's
  source (`--source` overrides; service by default); it returns None and the
  reason without parts or for a part from a file. In `core.doctor`,
  `check_nominal_kind` gives errors for what no calibration changes (input units,
  output rate, the kind and number of the sensor's poles and zeros),
  `check_nominal_curve` warnings beyond 1 % of amplitude or 1 degree of phase in
  band (a calibration can explain them; a pole of the wrong sign shows as about
  180 degrees), and `stage_changes` names the stages that differ (type, gain,
  poles and zeros, coefficients, decimation). `io.inventory.evalresp_values`
  gives the complex response by evalresp; `evalresp_curve` is its amplitude.
- **End-to-end batteries**, `scripts/e2e/`, behind the validation numbers: the
  builds by the service, the local copy and files (`build_battery`), `nrlx
  response` and `nrlx doctor` through the command (`cli_battery`), `nrlx convert`
  through every format checked by obspy and scipy (`convert_battery`), `nrlx
  assets` through the commands (`assets_battery`), and every file of the local
  NRL with the doctor checks (`scan_nrl`). Random parts from a seed; not run by
  pytest. The mypy override for the missing stubs covers scipy too.
- **Local copy of the NRL**, `nrlx local sync|status|remove`. `sync` downloads
  the catalog, the code table and the zip of the whole NRL (`/combine` with
  `instconfig=full_NRL_v2_zip`, about 300 MB, streamed to disk by
  `io.service.download`), unzips it to `<cache>/nrl/NRL` in the layout of the zip
  (refusing a member that would leave the folder), notes the configurations of
  the catalog without a file (today one, the Lunitek LK-TEMP), then puts the
  three in place together and deletes the zip; a failure keeps the previous copy.
  `status` shows the folder, the files, the size and the date; `remove` asks
  first (`--yes` to skip) and keeps the catalog. `nrlx response --source local`
  and `Nrlx.response(source="local")` build without any request: a part alone is
  its file, two parts are combined by nrlx. `Nrlx.sync_local`, `Nrlx.local_tree`
  (set by `from_cache` when the copy exists), `Nrlx.part(instconfig, source)`,
  `Nrlx.local_file`, and `io.local` (`get_tree_dir`, `get_part_file`,
  `extract_tree`, `missing_parts`, `install_tree`, `remove_tree`, `tree_size`).
- `core.matching.varying_values`, the values of each parameter that differs
  between configurations.
- **Combination of any sensor and datalogger responses**, done by nrlx instead of
  the service: `core.combine.combine_responses(sensor, datalogger)` returns the
  combined obspy `Response` and notes. The sensor stages go up to the first stage
  with a voltage output and the datalogger stages start at the first with a
  voltage or empty input, so whole channels work as either part; an empty unit at
  the join takes the other side's (as the service does) and two different units
  are refused; the stages are renumbered; a polynomial sensor gives a polynomial
  divided by the powers of the datalogger gain. The poles and zeros are
  normalized to their stated gains: 12 % of the NRL sensors have a normalization
  factor that contradicts their gain by more than 1 % (every Eentec EA-140 by a
  factor 2, a REFTEK RT131A-02 by 8.8), which obspy applies as written when the
  channel sensitivity is at the sensor's frequency. The overall sensitivity is at
  the sensor's normalization frequency, at most a tenth of the output rate (the
  sensor's 1 Hz is out of band at 1 sps); a note says when the sensor gives less
  than half its gain there, as a geophone on a slow channel that sees none of its
  flat band (an HG-7 at 8 sps: 0.16 %). Checked against the service on real NRL
  parts (same stages) and against obspy on 300 random NRL pairs (the
  sensitivity obspy computes from the written file equals nrlx's to 1e-14).
- `core.gain`: the amplitude of the response stages computed directly, with the
  rules of evalresp (poles and zeros analog and digital, FIR plain and symmetric,
  filters with denominator, response lists, gain-only stages; a stage is
  renormalized to its gain when its frequency is not the sensitivity frequency, a
  FIR more than 2 % from normalized is divided by its sum), so that a sensitivity
  computed by nrlx is the one obspy deconvolves with. `response_amplitude(stages,
  frequency)` is the overall sensitivity.
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
- **`Nrlx.response(...)`** returns an obspy `Inventory` and the notes of the
  combination: each part (`sensor`, `datalogger`, `integrated`, `soh`) selected by
  keys and resolved before any request, one `/combine` request, a copy of the
  channel for each code (written as given), and the network, station, location,
  times and coordinates set by nrlx (the labels not given keep the service
  placeholders). The sensor or the datalogger, or both, can instead be obspy
  responses (`sensor_response=`, `datalogger_response=`, for example from your
  own files): the NRL part is then asked alone (`Nrlx.part(instconfig)`) and nrlx
  combines the two with `combine_responses`, whose notes it returns (empty with
  NRL parts only). Its request is `schema.response.ResponseInput`, which checks
  the parts (a sensor, a datalogger or both, an integrated or a state of health
  channel alone, a part by keys or by a response, a response with the other
  part), the channels, the times and the coordinates. `Nrlx.find(keys, element)`
  is `Catalog.find` with the code table. `io.inventory.label_channels` labels the
  channels, and `set_coordinates` works on an `Inventory`;
  `io.inventory.read_part(path, seed_id)` reads the response of a channel from any
  file obspy reads (picked by `NET.STA.LOC.CHA` when the file has several), and
  `placeholder_inventory` puts a response in the `XX.YY.00.ZZZ` channel of the
  service.
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
- `ResponseFormat` is a `Literal["resp", "stationxml", "sacpz"]` instead of an
  enum: pass `format="resp"` instead of `ResponseFormat.RESP`. `stationxml-resp`, left from
  `nrlx build`, is removed.
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
- **`nrlx doctor` checks the channels**, no longer only the structure of the
  file: it reads any file obspy reads (`FILE#NET.STA.LOC.CHA` for one channel),
  or SACPZ, and runs the tier 2 checks and the comparison with the NRL nominal
  (`--sensor`, `--datalogger`, `--integrated`, `--source`, `--no-nominal`,
  `--cache-root`, `--base-url`), in a table of one row per channel and five
  groups, then a line per warning or error (`--all` for every check). A file
  obspy cannot read is an error, with obspy's reason. Removed: `--format`, and
  the structural checks of the file (`check_response`, `check_resp`,
  `check_stationxml`, `infer_format`), which said little more once obspy had
  failed to read it.
- **Removed, replaced by `nrlx response`**: `nrlx browse` (summary, elements,
  manufacturers, models, configs, show) and `nrlx build`, with its
  `--sensor-instconfig`/`--sensor-keys` style flags, `--merge-channels` (one file
  with every channel is now the default, `--split` the other way) and `--zip`.
- The errors are printed on stderr.
- The README warns about dataless SEED written by obspy: its writer does not split
  a blockette over 9999 bytes (a FIR of more than about 415 coefficients), so the
  file is corrupt from that stage on; nrlx reads dataless and never writes it.

### Fixed

- **`nrlx doctor` no longer crashes on a response evalresp refuses** (stages out
  of order, a units break, a sensitivity of 0, a stage removed): the comparison
  with the nominal reports "curve not computed by evalresp" as an error and the
  tier 2 findings explain why. Found by injecting 14 kinds of faults in 10 NRL
  builds: 31 of 127 runs ended in a traceback before.
- **`nrlx doctor` takes COUNT and COUNTS as the same units** in the sensitivity,
  whatever the case: a sensitivity in COUNTS over stages ending in COUNT was an
  error (30 of the 39 errors on the real RESIF file FR.CIEL).
- **`nrlx doctor`: a sensitivity stated at or above Nyquist** that its stages do
  not give is a warning naming the cause ("state the sensitivity in the passband"),
  no longer an error: there the anti-alias filters cut the stages, so the ratio
  (x2.8e6 on FR.CIEL LH, whose value is right at 0.05 Hz) says where the
  sensitivity is, not that its value is wrong. In band it stays an error.
- **`nrlx doctor`: a stage with only a gain passes the units through.** StationXML
  writes no units for such a stage; it was read as a units break and a last stage
  in NONE (35 of the 38 errors on the real SCEDC file CI.PAS). A channel whose
  stages state no output units is an info.
- **`nrlx doctor`: auxiliary channels** (any instrument code other than the sensors
  H L P N G D F A J S V: mass position, temperature, voltage, clock, LOG, OCF)
  without a usable sensitivity or without a response are an info, no longer an
  error (`core.doctor.SENSORS`, used by `check_channel` and the command).
- **`nrlx doctor`: the normalization-factor warning** says "evalresp (which trusts
  A0) and tools that trust the stage gain give different amplitudes", true of any
  file, instead of naming the NRL service.
- **The SACPZ constant when the sensitivity is not at the frequency of A0.**
  SACPZ writes CONSTANT = A0 × the overall sensitivity (rdseed, IRIS, obspy),
  right only when A0 normalizes the poles and zeros at the frequency of the
  sensitivity; StationXML does not require it, and nrlx caps the sensitivity
  frequency of slow channels. `write_inventory` normalizes the first poles and
  zeros stage of a copy at the sensitivity frequency (obspy's
  `calculate_normalization_factor`) before obspy writes the SACPZ. On 45 random
  NRL builds, 6 SACPZ were 13 to 100 % off in band (geophones on 1 to 50 sps
  channels); each is now within 1 %. A channel whose first poles and zeros stage
  is digital is refused, as obspy cannot write it.
- **The rate of a RESP below 0.5 sps.** obspy reads the rate of a RESP file as
  the input rate of the last decimation over its factor, rounded to an integer,
  so a 0.1 sps channel read 0; `io.inventory.read_channels` gives such a channel
  the exact output rate of its decimations (`core.combine.output_rate`), for
  `nrlx convert`, `nrlx assets add` and `--sensor-file`/`--datalogger-file`.
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
- **`nrlx convert` skips the channels a format cannot hold**, with a note listing
  them by reason, instead of refusing the whole file (a station with SOH channels
  to SACPZ); none held is still an error. `io.inventory.refusal` says why a format
  cannot hold a channel and `writable_channels` keeps the others; `write_inventory`
  refuses with the same rule (`Cannot write FORMAT: ID: reason`). RESP now also
  refuses a channel without stages, sensitivity or polynomial (obspy reads it back
  as no response) and a stage numbered 0, the number RESP keeps for the
  sensitivity (the stage was lost).
- `nrlx convert` and `nrlx doctor` refuse a file without channels
  (`No channel in FILE`) instead of writing an empty file or crashing.
- The check of a converted file no longer crashes or refuses a lossless file when
  evalresp cannot compute the input (no stages, a polynomial of more than 3
  coefficients, `Illegal RESP format`): the curve is noted as not checked. A file
  read back that evalresp cannot compute is an error. A RESP with a channel
  polynomial and polynomial stages compares the stages, as obspy drops its stage 0
  on reading (false "reads back inf different").
- SACPZ of poles and zeros in Hz: converted to rad/s before obspy's writer, which
  crashes on poles without uncertainties.
- RESP keeps the fraction of a second of the epochs (`2022,112,05:53:33.7490`),
  leaves out the stage 0 of a sensitivity without value (it crashed), and the
  gain of a stage without one, which it wrote as 0 (evalresp refused the file).
- `nrlx doctor`: a sensitivity without input units (the NRL datalogger parts) is
  no longer an error against the units of the stages.
- The sdist no longer includes the local `.claude/` folder (now git-ignored).

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
