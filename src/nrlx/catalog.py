"""Typed, immutable view of a local NRL catalog.

``Catalog.from_file`` parses the downloaded ``/catalog`` JSON once into a frozen
tree of ``Element`` -> ``Manufacturer`` -> ``Model`` -> ``Configuration``. Query
methods filter that in-memory tree;
nothing re-reads or mutates it afterward.


"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, cast

from nrlx.exceptions import NrlxCacheError


class ElementKind(
    str,
    Enum
):
    """Top-level NRL catalog element kinds."""

    SENSOR = "sensor"
    DATALOGGER = "datalogger"


@dataclass(frozen=True)
class Configuration:
    """A single response configuration leaf from the NRL catalog.

    Args:
        element: Top-level element group name, for example ``sensor``.
        manufacturer: Manufacturer name.
        model: Model name.
        instconfig: NRL instrument configuration identifier, ready to pass
            to the ``/combine`` endpoint.
        version: Configuration version string.
        description: Human-readable summary of the configuration.
        parameters: Parsed parameter name/value pairs for this configuration.


    """
    element: str
    manufacturer: str
    model: str
    instconfig: str
    version: str
    description: str = ""
    parameters: dict[str, str] = field(default_factory=dict)

    def matches(self, key: str) -> bool:
        """Return True if ``key`` matches anywhere in this configuration.

        Case-insensitive substring check across manufacturer, model,
        instconfig, description, and every parameter value - the building
        block for ObsPy-v1-style key lists (unordered, ANDed by the caller).


        """
        haystacks = (
            self.manufacturer,
            self.model,
            self.instconfig,
            self.description,
            *self.parameters.values(),
        )
        return any(_matches(key, haystack) for haystack in haystacks)


@dataclass(frozen=True)
class Model:
    """A model entry inside an NRL manufacturer.

    Args:
        element: Top-level element group name.
        manufacturer: Manufacturer name.
        name: Model name.
        detail: Manufacturer-provided notes about this model.


    """
    element: str
    manufacturer: str
    name: str
    detail: str = ""
    _configurations: tuple[Configuration, ...] = field(
        default_factory=tuple,
        repr=False
    )

    @property
    def configuration_count(self) -> int:
        return len(self._configurations)

    def configurations(
        self,
        *,
        instconfig: str | None = None
    ) -> tuple[Configuration, ...]:
        """Return configurations under this model, optionally filtered by instconfig."""
        return tuple(
            c for c in self._configurations if _matches(instconfig, c.instconfig)
        )


@dataclass(frozen=True)
class Manufacturer:
    """A manufacturer entry inside an NRL element group.

    Args:
        element: Top-level element group name.
        name: Manufacturer name.
        detail: NRL-provided notes about this manufacturer.


    """
    element: str
    name: str
    detail: str = ""
    _models: tuple[Model, ...] = field(default_factory=tuple, repr=False)

    @property
    def model_count(self) -> int:
        return len(self._models)

    @property
    def configuration_count(self) -> int:
        return sum(model.configuration_count for model in self._models)

    def models(
        self,
        *,
        name: str | None = None
    ) -> tuple[Model, ...]:
        """Return models under this manufacturer, optionally filtered by name."""
        return tuple(m for m in self._models if _matches(name, m.name))


@dataclass(frozen=True)
class Element:
    """A top-level NRL catalog element group, for example ``sensor``.

    Args:
        name: Element group name.
        detail: NRL-provided notes about this element group.


    """
    name: str
    detail: str = ""
    _manufacturers: tuple[Manufacturer, ...] = field(default_factory=tuple, repr=False)

    @property
    def manufacturer_count(self) -> int:
        return len(self._manufacturers)

    @property
    def model_count(self) -> int:
        return sum(manufacturer.model_count for manufacturer in self._manufacturers)

    @property
    def configuration_count(self) -> int:
        return sum(
            manufacturer.configuration_count for manufacturer in self._manufacturers
        )

    def manufacturers(self, *, name: str | None = None) -> tuple[Manufacturer, ...]:
        """Return manufacturers under this element, optionally filtered by name."""
        return tuple(m for m in self._manufacturers if _matches(name, m.name))


@dataclass(frozen=True)
class Summary:
    """Summary information for a local NRL catalog.

    Args:
        path: Path to the local catalog file.
        format_version: NRL catalog format version.
        element_count: Number of top-level element groups.
        manufacturer_count: Number of manufacturers across all groups.
        model_count: Number of models across all manufacturers.
        configuration_count: Number of response configurations.


    """
    path: Path
    format_version: str
    element_count: int
    manufacturer_count: int
    model_count: int
    configuration_count: int


@dataclass(frozen=True)
class Catalog:
    """A parsed local NRL catalog.

    Args:
        path: Path to the local catalog file this was parsed from.
        format_version: NRL catalog format version.


    """
    path: Path
    format_version: str
    _elements: tuple[Element, ...] = field(default_factory=tuple, repr=False)

    @classmethod
    def from_file(cls, catalog_file: Path) -> Catalog:
        """Parse a local NRL catalog JSON file into a typed catalog tree.

        Args:
            catalog_file: Path to the downloaded NRL catalog file.

        Returns:
            Catalog with the full element/manufacturer/model/configuration tree.

        Raises:
            NrlxCacheError: If the catalog file is missing, unreadable, or invalid.


        """
        raw = _load_raw(catalog_file)
        root = raw.get("NRLCatalog")
        if not isinstance(root, dict):
            raise NrlxCacheError("Invalid catalog: missing NRLCatalog root object.")

        elements = tuple(_parse_element(e) for e in _as_list(root.get("element")))

        return cls(
            path=catalog_file,
            format_version=_str_field(root, "formatversion"),
            _elements=elements
        )

    @property
    def element_count(self) -> int:
        return len(self._elements)

    @property
    def manufacturer_count(self) -> int:
        return sum(element.manufacturer_count for element in self._elements)

    @property
    def model_count(self) -> int:
        return sum(element.model_count for element in self._elements)

    @property
    def configuration_count(self) -> int:
        return sum(element.configuration_count for element in self._elements)

    @property
    def summary(self) -> Summary:
        """Return this catalog's element/manufacturer/model/config counts."""
        return Summary(
            path=self.path,
            format_version=self.format_version,
            element_count=self.element_count,
            manufacturer_count=self.manufacturer_count,
            model_count=self.model_count,
            configuration_count=self.configuration_count
        )

    def elements(
        self,
        *,
        name: str | None = None
    ) -> tuple[Element, ...]:
        """Return element groups, optionally filtered by name."""
        return tuple(e for e in self._elements if _matches(name, e.name))

    def manufacturers(
        self,
        *,
        element: str | None = None,
        name: str | None = None
    ) -> tuple[Manufacturer, ...]:
        """Return manufacturers, optionally filtered by element group and name."""
        return tuple(
            manufacturer
            for el in self.elements(name=element)
            for manufacturer in el.manufacturers(name=name)
        )

    def models(
        self,
        *,
        element: str | None = None,
        manufacturer: str | None = None,
        name: str | None = None
    ) -> tuple[Model, ...]:
        """Return models, optionally filtered by element group, manufacturer, name."""
        return tuple(
            model
            for el in self.elements(name=element)
            for mfr in el.manufacturers(name=manufacturer)
            for model in mfr.models(name=name)
        )

    def configurations(
        self,
        *,
        element: str | None = None,
        manufacturer: str | None = None,
        model: str | None = None,
        instconfig: str | None = None
    ) -> tuple[Configuration, ...]:
        """Return configurations, optionally filtered down the full hierarchy."""
        return tuple(
            configuration
            for el in self.elements(name=element)
            for mfr in el.manufacturers(name=manufacturer)
            for mdl in mfr.models(name=model)
            for configuration in mdl.configurations(instconfig=instconfig)
        )

    def search(
        self,
        query: str,
        *,
        element: str | None = None
    ) -> tuple[Configuration, ...]:
        """Search configurations by a single free-text substring match.

        Unlike configurations(), which ANDs each filter against its own field,
        this ORs the query across manufacturer, model, and instconfig - useful
        when you don't know which field a term belongs to.

        Args:
            query: Substring to match against manufacturer, model, or instconfig.
            element: Optional element group filter, applied before the search.

        Returns:
            Matching configurations, in catalog order.


        """
        return tuple(
            configuration
            for el in self.elements(name=element)
            for mfr in el.manufacturers()
            for mdl in mfr.models()
            for configuration in mdl.configurations()
            if _matches(query, mfr.name)
            or _matches(query, mdl.name)
            or _matches(query, configuration.instconfig)
        )


def _parse_configuration(
    element_name: str,
    manufacturer_name: str,
    model_name: str,
    raw: dict[str, Any]
) -> Configuration:
    parameters_raw = raw.get("parameters")
    parameters = dict(parameters_raw) if isinstance(parameters_raw, dict) else {}

    return Configuration(
        element=element_name,
        manufacturer=manufacturer_name,
        model=model_name,
        instconfig=_str_field(raw, "instconfig"),
        version=_str_field(raw, "version"),
        description=_str_field(raw, "description"),
        parameters=parameters
    )


def _parse_model(
    element_name: str,
    manufacturer_name: str,
    raw: dict[str, Any]
) -> Model:
    name = _str_field(raw, "name")
    configurations = tuple(
        _parse_configuration(element_name, manufacturer_name, name, c)
        for c in _as_list(raw.get("configuration"))
    )

    return Model(
        element=element_name,
        manufacturer=manufacturer_name,
        name=name,
        detail=_str_field(raw, "detail"),
        _configurations=configurations
    )


def _parse_manufacturer(
    element_name: str,
    raw: dict[str, Any]
) -> Manufacturer:
    name = _str_field(
        raw,
        "name"
    )
    models = tuple(
        _parse_model(element_name, name, m) for m in _as_list(raw.get("model"))
    )

    return Manufacturer(
        element=element_name,
        name=name,
        detail=_str_field(raw, "detail"),
        _models=models
    )


def _parse_element(raw: dict[str, Any]) -> Element:
    name = _str_field(
        raw,
        "name"
    )
    manufacturers = tuple(
        _parse_manufacturer(name, m) for m in _as_list(raw.get("manufacturer"))
    )

    return Element(
        name=name,
        detail=_str_field(
            raw,
            "detail"
        ),
        _manufacturers=manufacturers
    )


def _load_raw(catalog_file: Path) -> dict[str, Any]:
    """Load and parse a local NRL catalog JSON file.

    Args:
        catalog_file: Path to the downloaded NRL catalog file.

    Returns:
        Parsed catalog dictionary.

    Raises:
        NrlxCacheError: If the catalog file is missing, unreadable, or invalid.


    """
    if not catalog_file.exists():
        raise NrlxCacheError(
            f"Catalog file not found: {catalog_file}. Run 'nrlx sync'."
        )

    try:
        raw_text = catalog_file.read_text(encoding="utf-8")
        return cast(dict[str, Any], json.loads(raw_text))
    except json.JSONDecodeError as exc:
        raise NrlxCacheError(f"Invalid catalog JSON: {catalog_file}") from exc
    except OSError as exc:
        raise NrlxCacheError(f"Failed to read catalog: {catalog_file}") from exc


def _as_list(value: Any) -> list[dict[str, Any]]:
    """Return a catalog field as a list of dictionaries.

    Args:
        value: Raw JSON field value.

    Returns:
        List of dictionary entries. Missing or invalid values become an empty list.


    """
    if isinstance(
        value,
        list
    ):
        return [item for item in value if isinstance(item, dict)]

    if isinstance(
        value,
        dict
    ):
        return [value]

    return []


def _matches(needle: str | None, haystack: str) -> bool:
    """Case-insensitive substring match, treating ``None`` as a wildcard."""
    return needle is None or needle.lower() in haystack.lower()


def _str_field(raw: dict[str, Any], key: str) -> str:
    """Read a catalog field as a string, defaulting to ``""`` when missing."""
    return str(raw.get(key, ""))
