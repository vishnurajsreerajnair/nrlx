"""Text matching of the catalog filters"""

from __future__ import annotations


def contains(text: str, query: str | None) -> bool:
    """Whether the text contains the query, case-insensitive

    A query None is contained in every text, as a filter not specified.

    Args:
        text: text to search, for example a manufacturer name.
        query: text to find, None for any text.

    Returns:
        whether the query is in the text.


    """
    contained = query is None or query.lower() in text.lower()

    return contained


def contains_keys(texts: list[str], keys: list[str]) -> bool:
    """Whether each of the keys is contained in at least one of the texts

    The keys are unordered and case-insensitive, as the key lists of the ObsPy NRL
    v1 client: every key must match, each in any of the texts. No keys match any
    texts.

    Args:
        texts: texts to search, for example the names and parameters of a
            configuration.
        keys: texts to find.

    Returns:
        whether all the keys are found.


    """
    contained = all(any(contains(text, key) for text in texts) for key in keys)

    return contained
