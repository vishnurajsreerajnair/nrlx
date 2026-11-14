"""Structs of the selection of a sensor or datalogger configuration"""

from __future__ import annotations

import msgspec


class InstrumentInput(
    msgspec.Struct,
    kw_only=True,
    forbid_unknown_fields=True,
    frozen=True,
):
    """Selection of a sensor or datalogger configuration of the NRL catalog

    The configuration is selected by its exact instconfig, or by filters matched
    against the catalog, case-insensitive: the manufacturer and model names contain
    manufacturer and model, and each of the keys is found in the manufacturer, the
    model, the instconfig, the description, or a parameter name or value of the
    configuration (ObsPy NRL v1 style). The filters must match a single configuration.

    Args:
        instconfig: exact instconfig, None to select by the filters.
        manufacturer: text in the manufacturer name, None for any manufacturer.
        model: text in the model name, None for any model.
        keys: texts found in the configuration, all of them.


    """

    instconfig: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    keys: list[str] = []

    def __post_init__(self) -> None:
        # the exact instconfig leaves nothing to filter
        filtered = (
            self.manufacturer is not None or self.model is not None or bool(self.keys)
        )
        if self.instconfig is not None and filtered:
            raise ValueError(
                "Select by instconfig or by manufacturer, model and keys, not both. "
                f"Provided instconfig {self.instconfig}, manufacturer "
                f"{self.manufacturer}, model {self.model}, keys {self.keys}"
            )
