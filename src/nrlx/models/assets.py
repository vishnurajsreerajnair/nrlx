"""The assets: StationXML files as built, by UID, versioned, in a SQLite file"""

from __future__ import annotations

import builtins
from datetime import UTC, datetime
from pathlib import Path

import msgspec
from obspy import Inventory
from obspy.core.inventory import Channel

from nrlx.core.assets import (
    PROVENANCE_SUBJECT,
    check_uid,
    column_holds,
    read_provenance,
    split_asset_keys,
)
from nrlx.core.convert import LOSSLESS_TOLERANCE
from nrlx.io.assets import (
    delete_rows,
    insert_asset,
    read_export,
    read_rows,
    read_text,
    set_deprecated,
    text_sha256,
    write_export,
)
from nrlx.io.inventory import (
    PLACEHOLDER_STATION,
    read_stationxml,
    response_difference,
    stationxml_text,
)
from nrlx.models.catalog import Catalog
from nrlx.schema.asset import AssetRow
from nrlx.schema.prefixes import PrefixInput


class Assets(msgspec.Struct, frozen=True, kw_only=True):
    """The assets of a database, with the catalog to pick them by NRL keys

    Args:
        db: file of the database (SQLite), created on the first add.
        catalog: catalog, for the keys on the NRL parts; None to pick by rate,
            units and version only.
        prefixes: code table, for the conditions named by a code (FR=100).


    """

    db: Path
    catalog: Catalog | None = None
    prefixes: builtins.list[PrefixInput] = []

    def add(self, inventory: Inventory, uid: str | None = None) -> AssetRow:
        """Store an inventory as the next version of an asset

        The UID is the station code of the inventory unless given. The variant
        (rate, input units, sensitivity, the NRL parts of the provenance comment)
        is the one of its channels, which must share one response. The text is
        read back before it is stored.

        Args:
            inventory: inventory as built, with its labels.
            uid: UID of the asset, None for the station code.

        Returns:
            the row stored, with its version.

        Raises:
            ValueError: if the UID is missing or not valid, the inventory has no
                channel with a response, its channels differ, its text does not
                read back the same, or the UID already has this response.
            OSError, sqlite3.Error: if the database cannot be written.


        """
        channels = [
            (f"{net.code}.{sta.code}.{cha.location_code}.{cha.code}", cha)
            for net in inventory
            for sta in net
            for cha in sta
        ]
        if not channels or any(cha.response is None for _, cha in channels):
            raise ValueError("An asset needs channels, each with a response.")

        # the UID: given, or the one station code that is not the placeholder
        stations = sorted({sta.code for net in inventory for sta in net})
        match (uid, stations):
            case (str(given), _):
                named = given
            case (None, [code]) if code != PLACEHOLDER_STATION:
                named = code
            case (None, [_]):
                raise ValueError(
                    f"The station is the placeholder {PLACEHOLDER_STATION}: give "
                    "a UID, or label the station."
                )
            case _:
                raise ValueError(
                    f"The file has the stations {', '.join(stations)}: give a UID."
                )
        named = check_uid(named)

        # one response for every channel: the variant of the asset
        variants = {channel_variant(cha) for _, cha in channels}
        if len(variants) > 1:
            raise ValueError(
                "The channels have different responses (rate, units or "
                "sensitivity): an asset holds one response, add them apart."
            )
        _, first = channels[0]
        rate, units, sensitivity = channel_variant(first)
        sensor, datalogger = channel_parts(first)

        # the text, read back the same
        text = stationxml_text(inventory)
        back = read_stationxml(text.encode("utf-8"))
        for (seedid, before), after in zip(
            channels, [cha for net in back for sta in net for cha in sta], strict=True
        ):
            difference = response_difference(
                before.response, after.response, before.sample_rate
            )
            if difference is not None and difference > LOSSLESS_TOLERANCE:
                raise ValueError(
                    f"{seedid} reads back {difference:.1e} different from its "
                    "StationXML text."
                )

        duplicate = self.duplicate_of(inventory, named)
        if duplicate is not None:
            undo = ""
            if duplicate.deprecated is not None:
                undo = " (deprecated: put it back with --undo)"
            raise ValueError(
                f"{named} already has this response as v{duplicate.version}{undo}."
            )
        row = AssetRow(
            uid=named,
            version=0,
            added=utc_now(),
            sample_rate=rate,
            input_units=units,
            sensitivity=sensitivity,
            sensor=sensor,
            datalogger=datalogger,
            channels=[seedid for seedid, _ in channels],
            sha256=text_sha256(text),
        )
        stored = insert_asset(self.db, row, text, keep_version=False)

        return stored

    def duplicate_of(self, inventory: Inventory, uid: str) -> AssetRow | None:
        """The version of an asset with the same response as an inventory

        The response of the first channel is compared with the first channel of
        each version, deprecated ones included, within LOSSLESS_TOLERANCE.

        Args:
            inventory: inventory to add.
            uid: UID of the asset.

        Returns:
            the first version with the same response, None if there is none.

        Raises:
            ValueError: if the database was written by a newer layout.
            sqlite3.Error: if the file is not a database.


        """
        first = next(cha for net in inventory for sta in net for cha in sta)
        same = [
            row
            for row in read_rows(self.db, uid)
            if row_difference(self.db, row, first) <= LOSSLESS_TOLERANCE
        ]
        duplicate = same[0] if same else None

        return duplicate

    def select(
        self,
        uid: str,
        keys: builtins.list[str] | None = None,
        version: int | None = None,
    ) -> AssetRow:
        """The version of an asset that keys or a version number pick

        Without a version, the latest version in use whose NRL parts match every
        key (as in nrlx response), and whose rate and units match rate= and
        units=; the versions left must be of one variant.

        Args:
            uid: UID of the asset.
            keys: keys of the variant, None or empty for any.
            version: the version, deprecated or not; None for the latest in use.

        Returns:
            the row.

        Raises:
            LookupError: if the UID, the version or a match is missing.
            ValueError: if the keys match several variants, a key on the NRL parts
                has no catalog, or a condition name stands for several parameters.
            sqlite3.Error: if the file is not a database.


        """
        rows = read_rows(self.db, uid)
        if not rows:
            known = sorted({row.uid for row in read_rows(self.db)})
            raise LookupError(
                f"No asset {uid} in {self.db} (assets: {', '.join(known) or 'none'})."
            )
        if version is not None:
            picked = [row for row in rows if row.version == version]
            if not picked:
                raise LookupError(
                    f"{uid} has no version {version} (versions: "
                    f"{', '.join(str(row.version) for row in rows)})."
                )
        else:
            partkeys, columns = split_asset_keys(keys or [])
            if partkeys and self.catalog is None:
                raise ValueError(
                    "The keys on the NRL parts need the catalog: run nrlx sync."
                )
            picked = [
                row
                for row in rows
                if row.deprecated is None
                and all(
                    column_holds(row.sample_rate, row.input_units, condition)
                    for condition in columns
                )
                and all(self.part_matches(row, key) for key in partkeys)
            ]
            if not picked:
                wanted = " ".join(keys or []) or "no key"
                raise LookupError(f"No version of {uid} in use matches {wanted}.")
            variants = sorted(
                {
                    (row.sensor or "", row.datalogger or "", row.sample_rate or 0.0)
                    for row in picked
                }
            )
            if len(variants) > 1:
                shown = "; ".join(
                    f"v{row.version}: {row.sample_rate or 0:g} sps, "
                    f"{row.sensor or '?'}, {row.datalogger or '?'}"
                    for row in picked
                )
                raise ValueError(
                    f"{uid} has {len(variants)} variants for these keys ({shown}): "
                    "add a key (FR=100, rate=40) or --version."
                )
        selected = picked[-1]

        return selected

    def get(
        self,
        uid: str,
        keys: builtins.list[str] | None = None,
        version: int | None = None,
    ) -> Inventory:
        """The StationXML of the version of an asset that keys or a version pick

        Args:
            uid: UID of the asset.
            keys: keys of the variant, None for any (see select).
            version: the version, None for the latest in use.

        Returns:
            the inventory, as it was added.

        Raises:
            LookupError: if the UID, the version or a match is missing.
            ValueError: if the keys match several variants (see select).
            sqlite3.Error: if the file is not a database.


        """
        row = self.select(uid, keys, version)
        inventory = read_stationxml(
            read_text(self.db, row.uid, row.version).encode("utf-8")
        )

        return inventory

    def deprecate(self, uid: str, version: int, undo: bool = False) -> None:
        """Deprecate a version, so that the keys no longer pick it, or undo it

        Args:
            uid: UID of the asset.
            version: its version.
            undo: True to put the version back in use.

        Raises:
            LookupError: if the UID has no such version.
            sqlite3.Error: if the database cannot be written.


        """
        set_deprecated(self.db, uid, version, None if undo else utc_now())

    def delete(self, uid: str, version: int | None = None) -> int:
        """Delete a version of an asset, or all of them

        Args:
            uid: UID of the asset.
            version: its version, None for every version.

        Returns:
            the number of versions deleted.

        Raises:
            LookupError: if nothing matches.
            sqlite3.Error: if the database cannot be written.


        """
        deleted = delete_rows(self.db, uid, version)

        return deleted

    def export_to(self, folder: Path) -> builtins.list[Path]:
        """Write every version as UID/vN.xml with a manifest.json, to share

        Args:
            folder: folder of the export, missing or empty.

        Returns:
            the files written, the manifest last.

        Raises:
            ValueError: if the folder is not empty.
            OSError: if a file cannot be written.
            sqlite3.Error: if the file is not a database.


        """
        rows = read_rows(self.db)
        texts = [read_text(self.db, row.uid, row.version) for row in rows]
        files = write_export(folder, rows, texts)

        return files

    def import_from(self, source: Path) -> tuple[int, int]:
        """Merge an export folder or another database into this one

        Each version keeps its UID and number. A version already here with the
        same SHA-256 is skipped; one with another SHA-256 stops the import before
        anything is written.

        Args:
            source: folder written by export_to, or a .sqlite database.

        Returns:
            the number of versions added, and of those skipped.

        Raises:
            FileNotFoundError: if the source is missing.
            ValueError: if a file of the export changed, or a version differs from
                the one here.
            OSError, sqlite3.Error: if a file or a database cannot be read or
                written.


        """
        if source.is_dir():
            rows, texts = read_export(source)
        elif source.is_file():
            rows = read_rows(source)
            texts = [read_text(source, row.uid, row.version) for row in rows]
        else:
            raise FileNotFoundError(f"No export or database at {source}.")
        here = {(row.uid, row.version): row.sha256 for row in read_rows(self.db)}
        conflicts = [
            f"{row.uid} v{row.version}"
            for row in rows
            if here.get((row.uid, row.version), row.sha256) != row.sha256
        ]
        if conflicts:
            raise ValueError(
                f"{', '.join(conflicts)} differ from the versions here: nothing "
                "imported."
            )
        new = [
            (row, text)
            for row, text in zip(rows, texts, strict=True)
            if (row.uid, row.version) not in here
        ]
        for row, text in new:
            insert_asset(self.db, row, text, keep_version=True)

        return len(new), len(rows) - len(new)

    def part_matches(self, row: AssetRow, key: str) -> bool:
        """Whether a key matches the sensor or the datalogger of a version

        Args:
            row: version of an asset.
            key: key on the NRL parts, as in nrlx response.

        Returns:
            whether it matches one of the NRL parts in the catalog.

        Raises:
            ValueError: if a condition name stands for several parameters.


        """
        matches = False
        if self.catalog is not None:
            codes = [(prefix.prefix, prefix.description) for prefix in self.prefixes]
            parts = [row.sensor, row.datalogger]
            found = [
                catalogrow
                for catalogrow in self.catalog.get_configurations()
                if catalogrow[3].instconfig in parts
            ]
            matches = any(
                self.catalog.match_rows([catalogrow], [key], codes)
                for catalogrow in found
            )

        return matches

    # last: a method named list would shadow the builtin in the annotations above
    def list(self, uid: str | None = None) -> builtins.list[AssetRow]:
        """The versions of the assets, by UID then version, without their text

        Args:
            uid: UID of the asset, None for every asset.

        Returns:
            the rows.

        Raises:
            sqlite3.Error: if the file is not a database.


        """
        rows = read_rows(self.db, uid)

        return rows


def channel_variant(channel: Channel) -> tuple[float | None, str, float | None]:
    """Sample rate, input units and sensitivity of a channel

    Args:
        channel: channel with a response.

    Returns:
        the rate (None without one), the input units of the sensitivity, of the
        polynomial or of the first stage, and the sensitivity (None without one).


    """
    response = channel.response
    sensitivity = response.instrument_sensitivity
    polynomial = response.instrument_polynomial
    stages = response.response_stages
    if sensitivity is not None and sensitivity.input_units:
        units = sensitivity.input_units
    elif polynomial is not None:
        units = polynomial.input_units or ""
    else:
        units = (stages[0].input_units or "") if stages else ""
    value = sensitivity.value if sensitivity is not None else None

    return channel.sample_rate or None, units, value


def channel_parts(channel: Channel) -> tuple[str | None, str | None]:
    """Sensor and datalogger of a channel, from its provenance comment

    Args:
        channel: channel, maybe built by nrlx.

    Returns:
        the instconfig of the sensor (or integrated instrument) and of the
        datalogger (or state of health channel), file for a part from a file, None
        when the channel does not say.


    """
    parts = [
        part
        for comment in channel.comments
        if comment.subject == PROVENANCE_SUBJECT
        for part in read_provenance(comment.value)
    ]
    found = dict(parts)
    sensor = found.get("sensor", found.get("integrated"))
    datalogger = found.get("datalogger", found.get("soh"))

    return sensor, datalogger


def row_difference(db: Path, row: AssetRow, channel: Channel) -> float:
    """Difference between the first channel of a version and a channel

    Args:
        db: file of the database.
        row: version of an asset.
        channel: channel compared.

    Returns:
        the largest relative difference of the curves, inf when it cannot be
        compared (no sensitivity on either side).


    """
    stored = read_stationxml(read_text(db, row.uid, row.version).encode("utf-8"))
    first = next(cha for net in stored for sta in net for cha in sta)
    difference = response_difference(
        first.response, channel.response, first.sample_rate
    )
    same_rate = (first.sample_rate or None) == (channel.sample_rate or None)
    compared = difference if difference is not None and same_rate else float("inf")

    return compared


def utc_now() -> str:
    """The current time, UTC, ISO 8601 to the second

    Returns:
        for example 2026-11-15T10:30:00+00:00.


    """
    now = datetime.now(UTC).replace(microsecond=0).isoformat()

    return now
