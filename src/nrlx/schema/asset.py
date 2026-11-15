"""The assets: a row of the database, and the manifest of an export"""

from __future__ import annotations

import msgspec

# version of the manifest of an export
MANIFEST_VERSION = 1


class AssetRow(msgspec.Struct, frozen=True, kw_only=True):
    """One version of an asset: a StationXML file as built, under a UID

    Args:
        uid: UID of the asset, by default its station code.
        version: version, one sequence per UID.
        added: when it was added, UTC, ISO 8601.
        deprecated: when it was deprecated, UTC, None while in use.
        sample_rate: sample rate of its channels, None without digital stages.
        input_units: input units of its channels, for example M/S.
        sensitivity: overall sensitivity of its channels, None for a polynomial.
        sensor: instconfig of the sensor (or of the integrated instrument), file
            for a sensor from a file, None if unknown.
        datalogger: instconfig of the datalogger (or of the state of health
            channel), file for a datalogger from a file, None if unknown.
        channels: SEED id of each channel.
        sha256: SHA-256 of the StationXML text.


    """

    uid: str
    version: int
    added: str
    deprecated: str | None = None
    sample_rate: float | None = None
    input_units: str = ""
    sensitivity: float | None = None
    sensor: str | None = None
    datalogger: str | None = None
    channels: list[str] = []
    sha256: str = ""


class ManifestInput(msgspec.Struct, frozen=True):
    """manifest.json of an export: every row, the files are UID/vN.xml beside it

    Args:
        manifest_version: version of the manifest layout.
        assets: the rows, without their StationXML text.


    """

    manifest_version: int = MANIFEST_VERSION
    assets: list[AssetRow] = []
