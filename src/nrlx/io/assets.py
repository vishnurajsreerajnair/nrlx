"""The database of the assets (SQLite) and the files of an export

One row per version of an asset, with the StationXML text as built. The database
is a single file, by default ROOT/assets.sqlite in the cache; an export is a
folder of UID/vN.xml files with a manifest.json, to share or to look at.


"""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import msgspec

from nrlx.io.cache import get_cache_root
from nrlx.schema.asset import AssetRow, ManifestInput

# version of the layout of the database, in PRAGMA user_version
LAYOUT_VERSION = 1

# name of the database in the cache, and of the manifest of an export
ASSETS_FILE = "assets.sqlite"
MANIFEST_FILE = "manifest.json"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS assets (
    uid         TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    added       TEXT    NOT NULL,
    deprecated  TEXT,
    sample_rate REAL,
    input_units TEXT    NOT NULL,
    sensitivity REAL,
    sensor      TEXT,
    datalogger  TEXT,
    channels    TEXT    NOT NULL,
    sha256      TEXT    NOT NULL,
    stationxml  TEXT    NOT NULL,
    PRIMARY KEY (uid, version)
)
"""

# the columns of a row, in the order of AssetRow, without the text
ROW_COLUMNS = (
    "uid, version, added, deprecated, sample_rate, input_units, sensitivity, "
    "sensor, datalogger, channels, sha256"
)


def get_assets_file(cache_root: Path | None = None) -> Path:
    """Path of the database of the assets in the cache, ROOT/assets.sqlite

    Args:
        cache_root: custom root folder, None for the platform cache folder of the
            user.

    Returns:
        path of the database, which may not exist yet.


    """
    assets_file = get_cache_root(cache_root) / ASSETS_FILE

    return assets_file


def text_sha256(text: str) -> str:
    """SHA-256 of a StationXML text, as stored with each version

    Args:
        text: StationXML text.

    Returns:
        the hexadecimal digest of its UTF-8 bytes.


    """
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    return digest


def open_database(path: Path) -> sqlite3.Connection:
    """Open the database, creating it and its table when missing

    Args:
        path: file of the database.

    Returns:
        the connection; the caller closes it.

    Raises:
        ValueError: if the database was written by a newer layout.
        OSError: if its folder cannot be created.
        sqlite3.Error: if the file is not a database.


    """
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    (layout,) = connection.execute("PRAGMA user_version").fetchone()
    if layout > LAYOUT_VERSION:
        connection.close()
        raise ValueError(
            f"{path} has the layout {layout} of a newer nrlx (this one reads "
            f"{LAYOUT_VERSION}): update nrlx."
        )
    with connection:
        connection.execute(CREATE_TABLE)
        connection.execute(f"PRAGMA user_version = {LAYOUT_VERSION}")

    return connection


def to_row(values: tuple[object, ...]) -> AssetRow:
    """A row of the table as an AssetRow, the channels split

    Args:
        values: the values of ROW_COLUMNS.

    Returns:
        the row.


    """
    (
        uid,
        version,
        added,
        deprecated,
        sample_rate,
        input_units,
        sensitivity,
        sensor,
        datalogger,
        channels,
        sha256,
    ) = values
    row = msgspec.convert(
        {
            "uid": uid,
            "version": version,
            "added": added,
            "deprecated": deprecated,
            "sample_rate": sample_rate,
            "input_units": input_units,
            "sensitivity": sensitivity,
            "sensor": sensor,
            "datalogger": datalogger,
            "channels": str(channels).split(",") if channels else [],
            "sha256": sha256,
        },
        AssetRow,
    )

    return row


def insert_asset(
    path: Path, row: AssetRow, stationxml: str, keep_version: bool
) -> AssetRow:
    """Store a version of an asset

    Args:
        path: file of the database.
        row: the row; its version is kept only with keep_version.
        stationxml: StationXML text of the asset.
        keep_version: True to store the version of the row (an import), False to
            take the next one of its UID.

    Returns:
        the row stored, with its version.

    Raises:
        ValueError: if the UID already has that version.
        OSError, sqlite3.Error: if the database cannot be written.


    """
    with closing(open_database(path)) as connection, connection:
        # the next version in the same transaction as the insert
        (latest,) = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM assets WHERE uid = ?", (row.uid,)
        ).fetchone()
        stored = row
        if not keep_version:
            stored = msgspec.structs.replace(row, version=latest + 1)
        try:
            connection.execute(
                f"INSERT INTO assets ({ROW_COLUMNS}, stationxml) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stored.uid,
                    stored.version,
                    stored.added,
                    stored.deprecated,
                    stored.sample_rate,
                    stored.input_units,
                    stored.sensitivity,
                    stored.sensor,
                    stored.datalogger,
                    ",".join(stored.channels),
                    stored.sha256,
                    stationxml,
                ),
            )
        except sqlite3.IntegrityError as err:
            raise ValueError(
                f"{stored.uid} already has a version {stored.version}."
            ) from err

    return stored


def read_rows(path: Path, uid: str | None = None) -> list[AssetRow]:
    """Rows of the database, without their text, by UID then version

    Args:
        path: file of the database; a missing file has no rows (and is not
            created).
        uid: UID of the rows, None for every UID.

    Returns:
        the rows.

    Raises:
        ValueError: if the database was written by a newer layout.
        sqlite3.Error: if the file is not a database.


    """
    rows: list[AssetRow] = list()
    if path.is_file():
        with closing(open_database(path)) as connection:
            query = f"SELECT {ROW_COLUMNS} FROM assets"
            if uid is None:
                found = connection.execute(f"{query} ORDER BY uid, version")
            else:
                found = connection.execute(
                    f"{query} WHERE uid = ? ORDER BY version", (uid,)
                )
            rows = [to_row(values) for values in found.fetchall()]

    return rows


def read_text(path: Path, uid: str, version: int) -> str:
    """StationXML text of a version of an asset

    Args:
        path: file of the database.
        uid: UID of the asset.
        version: its version.

    Returns:
        the StationXML text.

    Raises:
        LookupError: if the UID has no such version.
        ValueError: if the database was written by a newer layout.
        sqlite3.Error: if the file is not a database.


    """
    found = None
    if path.is_file():
        with closing(open_database(path)) as connection:
            found = connection.execute(
                "SELECT stationxml FROM assets WHERE uid = ? AND version = ?",
                (uid, version),
            ).fetchone()
    if found is None:
        raise LookupError(f"No version {version} of {uid} in {path}.")
    (text,) = found

    return str(text)


def set_deprecated(path: Path, uid: str, version: int, when: str | None) -> None:
    """Deprecate a version of an asset, or put it back in use

    Args:
        path: file of the database.
        uid: UID of the asset.
        version: its version.
        when: UTC of the deprecation, ISO 8601; None to put it back in use.

    Raises:
        LookupError: if the UID has no such version.
        ValueError: if the database was written by a newer layout.
        sqlite3.Error: if the database cannot be written.


    """
    changed = 0
    if path.is_file():
        with closing(open_database(path)) as connection, connection:
            changed = connection.execute(
                "UPDATE assets SET deprecated = ? WHERE uid = ? AND version = ?",
                (when, uid, version),
            ).rowcount
    if not changed:
        raise LookupError(f"No version {version} of {uid} in {path}.")


def delete_rows(path: Path, uid: str, version: int | None) -> int:
    """Delete a version of an asset, or every version of it

    Args:
        path: file of the database.
        uid: UID of the asset.
        version: its version, None for every version.

    Returns:
        the number of versions deleted.

    Raises:
        LookupError: if nothing matches.
        ValueError: if the database was written by a newer layout.
        sqlite3.Error: if the database cannot be written.


    """
    deleted = 0
    if path.is_file():
        with closing(open_database(path)) as connection, connection:
            if version is None:
                cursor = connection.execute("DELETE FROM assets WHERE uid = ?", (uid,))
            else:
                cursor = connection.execute(
                    "DELETE FROM assets WHERE uid = ? AND version = ?", (uid, version)
                )
            deleted = cursor.rowcount
    if not deleted:
        which = f"version {version} of {uid}" if version is not None else uid
        raise LookupError(f"No {which} in {path}.")

    return deleted


def write_export(folder: Path, rows: list[AssetRow], texts: list[str]) -> list[Path]:
    """Write an export: UID/vN.xml for each row, and the manifest

    Args:
        folder: folder of the export, missing or empty.
        rows: rows exported.
        texts: StationXML text of each row, in the same order.

    Returns:
        the files written, the manifest last.

    Raises:
        ValueError: if the folder is not empty.
        OSError: if a file cannot be written.


    """
    if folder.exists() and any(folder.iterdir()):
        raise ValueError(f"{folder} is not empty: export to a new folder.")
    files: list[Path] = list()
    for row, text in zip(rows, texts, strict=True):
        path = folder / row.uid / f"v{row.version}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        files.append(path)
    manifest = folder / MANIFEST_FILE
    manifest.write_bytes(
        msgspec.json.format(msgspec.json.encode(ManifestInput(assets=rows)))
    )
    files.append(manifest)

    return files


def read_export(folder: Path) -> tuple[list[AssetRow], list[str]]:
    """Rows and texts of an export, each file checked against the manifest

    Args:
        folder: folder written by write_export.

    Returns:
        the rows of the manifest, and the StationXML text of each.

    Raises:
        FileNotFoundError: if the manifest or a file is missing.
        ValueError: if the manifest is not valid, or a file does not have the
            SHA-256 of its row.
        OSError: if a file cannot be read.


    """
    try:
        manifest = msgspec.json.decode(
            (folder / MANIFEST_FILE).read_bytes(), type=ManifestInput
        )
    except msgspec.ValidationError as err:
        raise ValueError(f"{folder / MANIFEST_FILE} is not valid: {err}") from err
    except msgspec.DecodeError as err:
        raise ValueError(f"{folder / MANIFEST_FILE} is not JSON: {err}") from err
    texts = [
        (folder / row.uid / f"v{row.version}.xml").read_text(encoding="utf-8")
        for row in manifest.assets
    ]
    changed = [
        f"{row.uid}/v{row.version}.xml"
        for row, text in zip(manifest.assets, texts, strict=True)
        if text_sha256(text) != row.sha256
    ]
    if changed:
        raise ValueError(
            f"{folder}: {', '.join(changed)} changed since the export (SHA-256)."
        )

    return manifest.assets, texts
