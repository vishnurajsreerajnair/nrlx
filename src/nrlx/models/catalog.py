"""The NRL catalog, with its queries"""

from __future__ import annotations

import difflib

import msgspec

from nrlx.core.matching import (
    ANYWHERE,
    NOT_FOUND,
    START,
    compare,
    contains,
    resolve_parameter,
    sort_values,
    split_condition,
    varying_values,
    word_tier,
)
from nrlx.schema.catalog import (
    CatalogInput,
    ConfigurationInput,
    ElementInput,
    ManufacturerInput,
    ModelInput,
)
from nrlx.schema.prefixes import PrefixInput

# candidates listed by an ambiguous selection
MAX_CANDIDATES_SHOWN = 20

# names suggested for a word that matches nothing, and how close they must be
MAX_SUGGESTIONS = 3
SUGGESTION_CUTOFF = 0.6


class Found(msgspec.Struct, frozen=True):
    """Configurations matched by keys, with what helps to narrow them

    Args:
        rows: element, manufacturer, model and configuration of each match, in
            catalog order.
        varying: values of each parameter that differs between the rows, sorted,
            by parameter name.
        notes: how the words not found whole were found, for example "luni: start
            of Lunitek".
        hints: why nothing matches, only without rows, for example "lunitec: no
            match. Did you mean Lunitek?".


    """

    rows: list[tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput]]
    varying: dict[str, list[str]]
    notes: list[str]
    hints: list[str]


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
    ) -> list[tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput]]:
        """Configurations of the catalog, with their element, manufacturer and model

        Args:
            element_name: text in the element name, None for any element.

        Returns:
            element, manufacturer, model and configuration of each configuration.


        """
        configurations = [
            (element, manufacturer, model, configuration)
            for element, manufacturer, model in self.get_models(element_name)
            for configuration in model.configurations
        ]

        return configurations

    def find(
        self,
        keys: list[str],
        prefixes: list[PrefixInput],
        element_name: str | None = None,
    ) -> Found:
        """Configurations matched by keys: words and conditions on the parameters

        A word (luni, LP1, Q330HR_PG1) is found whole, at the start of a name or
        part, or anywhere; the rows kept have the lowest total tier of the words. A
        condition (FR=40, corner>=60, FR=100..500) holds on a parameter, named by
        its code or by the start of a word of its name. See core.matching.

        Args:
            keys: words and conditions, all of them, in any order.
            prefixes: code table, for the condition names that are codes.
            element_name: element searched, for example sensor; None for every
                element.

        Returns:
            the matched rows, the parameters that still vary, the notes on the
            words not found whole, and the hints when nothing matches.

        Raises:
            ValueError: if a condition name stands for several parameters, or a
                range has no bound.


        """
        rows = self.get_configurations(element_name)
        codes = [(prefix.prefix, prefix.description) for prefix in prefixes]
        words = [key for key in keys if not split_condition(key)]
        matched = self.match_rows(rows, keys, codes)

        # the parameters that still differ between the rows
        varying = varying_values(
            [configuration.parameters for *_, configuration in matched]
        )

        # the words found only at the start of a name or part, or inside a text
        notes: list[str] = list()
        for word in words:
            match sorted({self.row_tier(word, row) for row in matched}):
                case [tier] if tier == START:
                    starts = sorted(
                        {
                            text
                            for _, manufacturer, model, configuration in matched
                            for text in [
                                manufacturer.name,
                                model.name,
                                *configuration.instconfig.split("_"),
                            ]
                            if text.lower().startswith(word.lower())
                        }
                    )
                    shown = ", ".join(starts[:MAX_SUGGESTIONS])
                    notes.append(f"{word}: start of {shown}")
                case [tier] if tier == ANYWHERE:
                    notes.append(f"{word}: found inside a text only")
                case _:
                    pass

        # without rows, the keys that leave none
        hints: list[str] = list()
        if not matched:
            vocabulary = sorted(
                {
                    text
                    for _, manufacturer, model, configuration in rows
                    for text in [
                        manufacturer.name,
                        model.name,
                        *configuration.instconfig.split("_"),
                    ]
                }
            )
            for key in keys:
                # without the key a condition name can stand for several
                # parameters: the key gets no hint from the other keys
                otherkeys = [other for other in keys if other != key]
                try:
                    others = self.match_rows(rows, otherkeys, codes)
                except ValueError:
                    others = []
                isword = key in words
                if isword and not self.match_rows(rows, [key], codes):
                    close = difflib.get_close_matches(
                        key, vocabulary, MAX_SUGGESTIONS, SUGGESTION_CUTOFF
                    )
                    suggestion = f" Did you mean {', '.join(close)}?" if close else ""
                    hints.append(f"{key}: no match.{suggestion}")
                elif isword and others:
                    hints.append(f"{key}: no match with the other keys.")
                elif others:
                    hints.append(self.condition_hint(key, others, codes))
            if not hints:
                hints.append("No configuration matches all the keys together.")

        found = Found(rows=matched, varying=varying, notes=notes, hints=hints)

        return found

    def match_rows(
        self,
        rows: list[
            tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput]
        ],
        keys: list[str],
        codes: list[tuple[str, str]],
    ) -> list[tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput]]:
        """Rows matched by every key, the best by the lowest total tier of the words

        Args:
            rows: rows searched.
            keys: words and conditions, all of them.
            codes: code and parameter name of each code of the table.

        Returns:
            the matched rows, in their order.

        Raises:
            ValueError: if a condition name stands for several parameters, or a
                range has no bound.


        """
        words = [key for key in keys if not split_condition(key)]
        conditions = [condition for key in keys for condition in split_condition(key)]

        # every word somewhere, with its tier in each row
        tiered = [(row, [self.row_tier(word, row) for word in words]) for row in rows]
        tiered = [(row, tiers) for row, tiers in tiered if NOT_FOUND not in tiers]

        # the conditions, on the parameters of the rows of the words
        values: dict[str, list[str]] = dict()
        for (*_, configuration), _ in tiered:
            for name, value in configuration.parameters.items():
                values.setdefault(name, []).append(value)
        for name, operator, value in conditions:
            match resolve_parameter(name, value, codes, values):
                case [parameter]:
                    kept = list()
                    for row, tiers in tiered:
                        *_, configuration = row
                        present = configuration.parameters.get(parameter)
                        if present is not None and compare(present, operator, value):
                            kept.append((row, tiers))
                    tiered = kept
                case []:
                    tiered = []
                case parameters:
                    raise ValueError(
                        f"{name!r} stands for several parameters: "
                        f"{', '.join(parameters)}. Use one of them, or its code."
                    )

        # the lowest total tier of the words
        best = min([sum(tiers) for _, tiers in tiered], default=0)
        matched = [row for row, tiers in tiered if sum(tiers) == best]

        return matched

    def row_tier(
        self,
        word: str,
        row: tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput],
    ) -> int:
        """Tier of a word in a row, see core.matching.word_tier

        The whole names are the manufacturer, the model and the parameter values;
        the description and the parameter names are searched anywhere only.

        Args:
            word: key without an operator.
            row: element, manufacturer, model and configuration.

        Returns:
            WHOLE, START, ANYWHERE or NOT_FOUND.


        """
        _, manufacturer, model, configuration = row
        names = [manufacturer.name, model.name, *configuration.parameters.values()]
        texts = [
            *names,
            configuration.instconfig,
            configuration.description,
            *configuration.parameters.keys(),
        ]
        tier = word_tier(word, configuration.instconfig, names, texts)

        return tier

    def condition_hint(
        self,
        key: str,
        rows: list[
            tuple[ElementInput, ManufacturerInput, ModelInput, ConfigurationInput]
        ],
        codes: list[tuple[str, str]],
    ) -> str:
        """Why a condition matches none of the rows of the other keys

        Args:
            key: condition, for example FR=45.
            rows: rows matched by the other keys.
            codes: code and parameter name of each code of the table.

        Returns:
            the values of its parameter in the rows, or the parameters of the rows
            when its name stands for none of them.


        """
        [(name, _, wanted), *_] = split_condition(key)
        values: dict[str, list[str]] = dict()
        for *_, configuration in rows:
            for parameter, value in configuration.parameters.items():
                values.setdefault(parameter, []).append(value)
        match resolve_parameter(name, wanted, codes, values):
            case [parameter, *_]:
                present = sort_values(
                    [
                        configuration.parameters[parameter]
                        for *_, configuration in rows
                        if parameter in configuration.parameters
                    ]
                )
                hint = (
                    f"{key}: no match with the other keys. "
                    f"Values there: {', '.join(present)}"
                )
            case _:
                listed = ", ".join(sorted(values)) or "none"
                hint = (
                    f"{key}: no parameter {name!r} with the other keys. "
                    f"Parameters there: {listed}"
                )

        return hint

    def resolve(
        self,
        element_name: str,
        keys: list[str],
        prefixes: list[PrefixInput],
    ) -> ConfigurationInput:
        """The single configuration matched by the keys, see find

        Args:
            element_name: element of the configuration, for example sensor.
            keys: words and conditions, all of them.
            prefixes: code table, for the condition names that are codes.

        Returns:
            the matching configuration.

        Raises:
            LookupError: if no configuration matches, or more than one. The message
                gives the hints, or the parameters that still vary and the
                candidates, to pick the distinguishing keys.
            ValueError: if a condition name stands for several parameters, or a
                range has no bound.


        """
        found = self.find(keys, prefixes, element_name)

        match found.rows:
            case [(*_, configuration)]:
                resolved = configuration
            case []:
                hints = "\n".join(f"  {hint}" for hint in found.hints)
                raise LookupError(f"No {element_name} configuration matches.\n{hints}")
            case rows:
                # the parameters to add as keys, then a candidate for each line
                varying = "\n".join(
                    f"  {name}: {', '.join(values)}"
                    for name, values in found.varying.items()
                )
                candidates = "\n".join(
                    f"  {configuration.instconfig}"
                    for *_, configuration in rows[:MAX_CANDIDATES_SHOWN]
                )
                remaining = len(rows) - MAX_CANDIDATES_SHOWN
                more = f"\n  ...and {remaining} more" if remaining > 0 else ""
                raise LookupError(
                    f"Ambiguous {element_name} selection: {len(rows)} configurations "
                    f"match. Still varying:\n{varying}\n"
                    f"Candidates:\n{candidates}{more}"
                )

        return resolved
