"""Builds the configurable set of search queries for one executive.

WHY A TEMPLATE THAT NEEDS A MISSING VALUE IS SKIPPED, NOT FILLED BLANK:
A template like `'"{name}" "{company}"'` with no known company would
otherwise become `'"Ada Lovelace" ""'` — a malformed, useless query. This
module treats "the value this template needs isn't available" as "this
template doesn't apply to this executive right now," and simply omits it,
rather than sending a broken search.
"""

from __future__ import annotations

import string
from typing import Mapping, Sequence

_FORMATTER = string.Formatter()

#: The only placeholder names a query template may reference. Any other
#: placeholder is treated as unfillable (see `build_queries`).
_KNOWN_FIELDS = frozenset({"name", "company", "title"})


def build_queries(
    name: str,
    company: str | None,
    title: str | None,
    templates: Sequence[str],
) -> tuple[str, ...]:
    """Fill `templates` with `name`/`company`/`title`, in template order.

    Args:
        name: The executive's full name. Required — if blank, no query is
            generated (every default template references `{name}`).
        company: The executive's current company, or None/blank if unknown.
        title: The executive's current title, or None/blank if unknown.
        templates: Query templates, e.g. `'"{name}" "{company}"'`. A
            template referencing a placeholder with no value here is
            skipped entirely.

    Returns:
        Every successfully filled query, deduplicated (first occurrence
        wins), in template order.
    """

    values: Mapping[str, str] = {
        "name": name.strip(),
        "company": (company or "").strip(),
        "title": (title or "").strip(),
    }

    queries: list[str] = []
    seen: set[str] = set()

    for template in templates:
        fields = _referenced_fields(template)
        if not fields.issubset(_KNOWN_FIELDS):
            continue
        if any(not values[field_name] for field_name in fields):
            continue

        query = template.format(**values).strip()
        if not query or query in seen:
            continue
        seen.add(query)
        queries.append(query)

    return tuple(queries)


def _referenced_fields(template: str) -> set[str]:
    """Every `{field_name}` placeholder `template` references."""

    return {
        field_name for _, field_name, _, _ in _FORMATTER.parse(template) if field_name
    }
