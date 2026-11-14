"""Structs of the NRL catalog, as returned by the /catalog endpoint

The catalog is a tree: element (sensor, datalogger, ...), manufacturer, model and
configuration. The structs mirror the JSON of the service, with the lists named in
the plural. They accept unknown fields, so that a field added by the service does not
break the decoding.


"""

from __future__ import annotations

import msgspec


class ConfigurationInput(msgspec.Struct, frozen=True):
    """A response configuration, the leaf of the catalog

    Args:
        instconfig: identifier of the configuration, passed to the /combine
            endpoint. For example sensor_Streckeisen_STS-2_EG3_SG1500_LP120_STgroundVel.
        version: date of the last change of the configuration.
        description: summary of the configuration.
        parameters: values of the configuration by parameter name, for example
            Sensitivity.


    """

    instconfig: str
    version: str
    description: str = ""
    parameters: dict[str, str] = {}


class ModelInput(msgspec.Struct, frozen=True):
    """A model of a manufacturer, with its configurations

    Args:
        name: model name.
        detail: notes about the model.
        configurations: response configurations of the model.


    """

    name: str
    detail: str = ""
    configurations: list[ConfigurationInput] = msgspec.field(
        default_factory=list, name="configuration"
    )


class ManufacturerInput(msgspec.Struct, frozen=True):
    """A manufacturer of an element, with its models

    Args:
        name: manufacturer name.
        detail: notes about the manufacturer.
        models: models of the manufacturer.


    """

    name: str
    detail: str = ""
    models: list[ModelInput] = msgspec.field(default_factory=list, name="model")


class ElementInput(msgspec.Struct, frozen=True):
    """A top-level element of the catalog, for example sensor or datalogger

    Args:
        name: element name.
        detail: notes about the element.
        manufacturers: manufacturers of the element.


    """

    name: str
    detail: str = ""
    manufacturers: list[ManufacturerInput] = msgspec.field(
        default_factory=list, name="manufacturer"
    )


class CatalogInput(msgspec.Struct, frozen=True):
    """The NRL catalog, with its elements

    Args:
        format_version: version of the format of the catalog.
        detail: notes about the catalog.
        elements: top-level elements of the catalog.


    """

    format_version: float = msgspec.field(name="formatversion")
    detail: str = ""
    elements: list[ElementInput] = msgspec.field(default_factory=list, name="element")
