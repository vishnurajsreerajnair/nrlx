# nrlx

CLI and library for browsing the Nominal Response Library (NRL v2) of EarthScope and
building seismic instrument responses with its web service. Published on PyPI.

## Working with the user

- Change code only after an explicit go-ahead on the specific change. Agreeing with a direction is not approval: show the code first and ask.
- Discuss one decision at a time, listing exactly what changes in the existing code.
- Never run git write operations (commit, push, tag, merge, rebase, reset): prepare the working tree and give the user the commands.

## Code style

- Write the code in the black style (line length 88), with comments before the blocks and no string concatenation like `+ '\n'`. Run `ruff format --check` only as the final verification, never to format the code.
- Prefer explicit code: explicit arguments and return values (no `*args` or `**kwargs`), no containers whose content the reader has to know, no tricks that need a comment to be understood.
- Prefer self-contained functions: keep the orchestration (input, flags, output of the commands) in the command even when it repeats; share only the domain logic, which must stay in a single place.
- Prefer the Python idioms (unpacking, `_` for the ignored values, comprehensions, `match`) over new types or helper functions. The catalog queries return the tree nodes as tuples, unpacked by the callers.
- Every module starts with `from __future__ import annotations`, and the external types used in the annotations are imported. Use `X | None`, as ruff (UP) requires.
- Never write `return` inside loops or `if`s: assign a variable and return it once at the end.
- Never catch the generic `Exception`. Library code raises built-in exceptions (`ValueError`, `LookupError`, `FileNotFoundError`, `OSError`) or lets `httpx.HTTPError` and `msgspec` errors through; there is no custom exception hierarchy.
- Google docstrings (Args, Returns, Raises), ending with two blank lines.
- `mypy --strict` must pass: the model subclasses repeat `frozen=True`, as mypy requires.

## Structure

Each layer imports only the ones below it.

- `src/nrlx/schema/`: msgspec structs of every input (`...Input` classes). `catalog`, `prefixes` and `cache` mirror the NRL service JSON; `response` holds the request `ResponseInput`, with its validation, and the `ResponseFormat` literal (resp, stationxml, sacpz).
- `src/nrlx/models/`: models subclassing the input structs with the methods (`Catalog.get_configurations`, `Catalog.find` returning `Found`, `Catalog.resolve`), plus the library entry point `Nrlx` (catalog, code table and service: `find`, `response` returning an obspy `Inventory`).
- `src/nrlx/core/`: pure functions taking their arguments one by one, independent of the structs: matching of the keys (`split_condition`, `compare`, `word_tier`, `resolve_parameter`, `sort_values`, `varying_values`) and of the names (`contains`), SEED band codes (`band_codes`), `/combine` parameters and the combination of responses done by nrlx (`combine_responses`) and the notes on the responses kept as received (`received_notes`), the amplitude of the stages with the rules of evalresp (`gain`), the format of an output file and the amplitudes that check a file read back (`convert`), doctor checks.
- `src/nrlx/io/`: the NRL service (`get`, `get_url`, `download` streamed to a file), the local copy of the NRL (`local`: the tree of the zip in the cache, its paths, unzipping, checking and swapping), the local cache (paths, `read_catalog`, `decode_catalog`, `write_catalog`, and the same for the code table: `read_prefixes`, `decode_prefixes`, `write_prefixes`), obspy reading (`read_channels`, `read_part`), labelling (`label_channels`) and placing (`set_coordinates`) of StationXML, writing in the three formats and checking the file read back (`write_inventory`, `verify_written`), the RESP writer (`write_resp`) and the SACPZ reader (`read_sacpz`).
- `src/nrlx/tools/cmd/`: the typer commands. `__init__.py` builds the `nrlx` app (entry point `nrlx.tools.cmd:app`) from the modules `catalog` (status, sync, prefixes), `response`, `convert`, `doctor` and `local` (the `nrlx local` sub-app: sync, status, remove).

## Schema conventions

- The structs mirroring the NRL service JSON are frozen and accept unknown fields, so that a field added by the service does not break the decoding. Their lists are named in the plural, with `msgspec.field(name=...)` for the JSON key.
- The request structs are frozen, `kw_only=True` and `forbid_unknown_fields=True`.
- Nested fields that need methods use the model class (for example `CatalogFileInput.catalog: Catalog`), as in isamgeo-seismic-tools.
- Defaults live in the schema. Validation in `__post_init__` raising `ValueError`, only when the structure cannot express the rule.
- Selections resolve to exactly one configuration before any request to the service.

## Command conventions

- One `nrlx` binary with subcommands; the flags follow the existing CLI, with `-j`/`--version` on the root.
- Each command catches the specific exceptions it can get, prints `Error: ...` on stderr (Rich markup escaped) and exits with code 1. Only the commands print and exit.
- Output for humans with Rich tables and panels.

## Tests and tooling

- Install with `pip install -e '.[dev]'`, then `ruff check src tests`, `ruff format --check src tests`, `black --check src tests`, `mypy src`, `pytest`.
- `tests/lib/` tests the library, `tests/entrypoints/` the commands (typer `CliRunner`), with the shared data in `tests/data/`. `tests/conftest.py` has the fixtures, including `fake_service`, which replaces `httpx.get` and records the requests. Tests never hit the network.
- Record every change in `CHANGELOG.md` under `[Unreleased]`, without a version number until the user sets it.
