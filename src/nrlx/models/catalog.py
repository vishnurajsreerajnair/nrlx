"""The NRL catalog, with its queries"""

from __future__ import annotations

from nrlx.core.matching import contains, contains_keys
from nrlx.schema.catalog import (
    CatalogInput,
    ConfigurationInput,
    ElementInput,
    ManufacturerInput,
    ModelInput,
)

# candidates listed by an ambiguous selection
MAX_CANDIDATES_SHOWN = 20


class Catalog(CatalogInput, frozen=True):
    """The NRL catalog, decoded once and queried in memory

    The filters are case-insensitive texts contained in the names, None for any
    name. The queries of the lower levels return the nodes of the tree above them,
    in catalog order, for example (element, manufacturer, model) for the models.


    """

    def get_elements(self, name: str | None = None) -> list[ElementInput]:
        """Elements of the catalog, for example sensor and datalogger

        Args:
            name: text in the element name, None for any element.

        Returns:
            matching elements.


        """
        elements = [
            element for element in self.elements if contains(element.name, name)
        ]

        return elements

    def get_manufacturers(
        self,
        element_name: str | None = None,
        name: str | None = None,
    ) -> list[tuple[ElementInput, ManufacturerInput]]:
        """Manufacturers of the catalog, with their element

        Args:
            element_name: text in the element name, None for any element.
            name: text in the manufacturer name, None for any manufacturer.

        Returns:
            element and manufacturer of each matching manufacturer.


        """
        manufacturers = [
            (element, manufacturer)
            for element in self.get_elements(element_name)
            for manufacturer in element.manufacturers
            if contains(manufacturer.name, name)
        ]

        return manufacturers

    def get_models(
        self,
        element_name: str | None = None,
        manufacturer_name: str | None = None,
        name: str | None = None,
    ) -> list[tuple[ElementInput, ManufacturerInput, ModelInput]]:
        """Models of the catalog, with their element and manufacturer

        Args:
            element_name: text in the element name, None for any element.
            manufacturer_name: text in the manufacturer name, None for any
                manufacturer.
            name: text in the model name, None for any model.

        Returns:
            element, manufacturer and model of each matching model.


        """
        models = [
            (element, manufacturer, model)
            for element, manufacturer in self.get_manufacturers(
                element_name, manufacturer_name
            )
            for model in manufacturer.models
            if contains(model.name, name)
        ]

        return models

    def get_configurations(
        self,
        element_name: str | None = None,
        manufacturer_name: str | None = None,
        model_name: str | None = None,
        instconfig: str | None = None,
        keys: list[str] | None = None,
    ) -> list[tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput]]:
        """Configurations of the catalog, with their element, manufacturer and model

        Each filter narrows its own field, and the keys search every field: each key
        must be found in the manufacturer, the model, the instconfig, the description,
        or a parameter name or value. For example the key groundVel finds the
        configurations by a parameter value, Sensitivity by a parameter name.

        Args:
            element_name: text in the element name, None for any element.
            manufacturer_name: text in the manufacturer name, None for any
                manufacturer.
            model_name: text in the model name, None for any model.
            instconfig: text in the instconfig, None for any instconfig.
            keys: texts found in the configuration, all of them. None for no keys.

        Returns:
            element, manufacturer, model and configuration of each matching
            configuration.


        """
        configurations = [
            (element, manufacturer, model, configuration)
            for element, manufacturer, model in self.get_models(
                element_name, manufacturer_name, model_name
            )
            for configuration in model.configurations
            if contains(configuration.instconfig, instconfig)
            and contains_keys(
                [
                    manufacturer.name,
                    model.name,
                    configuration.instconfig,
                    configuration.description,
                    *configuration.parameters.keys(),
                    *configuration.parameters.values(),
                ],
                keys or [],
            )
        ]

        return configurations

    def resolve(
        self,
        element_name: str,
        manufacturer_name: str | None = None,
        model_name: str | None = None,
        instconfig: str | None = None,
        keys: list[str] | None = None,
    ) -> ConfigurationInput:
        """The single configuration matched by the filters, see get_configurations

        Args:
            element_name: text in the element name, for example sensor.
            manufacturer_name: text in the manufacturer name, None for any
                manufacturer.
            model_name: text in the model name, None for any model.
            instconfig: text in the instconfig, None for any instconfig.
            keys: texts found in the configuration, all of them. None for no keys.

        Returns:
            the matching configuration.

        Raises:
            LookupError: if no configuration matches, or more than one. The message
                lists the candidates, to pick the distinguishing keys.


        """
        configurations = [
            configuration
            for _, _, _, configuration in self.get_configurations(
                element_name, manufacturer_name, model_name, instconfig, keys
            )
        ]

        match configurations:
            case [configuration]:
                resolved = configuration
            case []:
                raise LookupError(
                    f"No {element_name} configuration found for the given filters."
                )
            case _:
                # a candidate for each line, the instconfigs are long
                candidates = "\n".join(
                    f"  {configuration.instconfig}"
                    for configuration in configurations[:MAX_CANDIDATES_SHOWN]
                )
                remaining = len(configurations) - MAX_CANDIDATES_SHOWN
                more = f"\n  ...and {remaining} more" if remaining > 0 else ""
                raise LookupError(
                    f"Ambiguous {element_name} selection: {len(configurations)} "
                    "configurations match the given filters. "
                    f"Candidates:\n{candidates}{more}"
                )

        return resolved
