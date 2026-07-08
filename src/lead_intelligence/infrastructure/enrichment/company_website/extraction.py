"""Executive extraction: given one leadership/about/team page's HTML, find
the people listed on it — name, title, biography, email, phone — using
DOM structure and class/id naming conventions, never AI.

WHY THIS IS A STRUCTURAL HEURISTIC, NOT AN AI CALL:
This task's scope explicitly excludes AI/LLM-based extraction. Leadership
pages overwhelmingly follow one of a small number of common patterns: a
repeated "card" per person (a `<div>`/`<li>`/`<article>` whose class or id
names the concept — "team-member," "leadership," "bio," "staff," ...),
containing a heading for the name, a smaller element for the title/role,
and optionally a paragraph biography and mailto:/tel: contact links. This
module looks for exactly that shape. It will miss unconventional layouts —
an acceptable, honestly-scoped limitation for Version 1, not a bug to
paper over with a model call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup
from bs4.element import Tag

#: Class/id substrings that mark an element as "this represents one person."
CONTAINER_HINTS: tuple[str, ...] = (
    "team-member",
    "teammember",
    "leadership",
    "exec",
    "staff",
    "bio",
    "person",
    "member",
    "management",
)

#: Class/id substrings that mark an element as "this is a title/role," as
#: distinct from the name heading found alongside it.
TITLE_HINTS: tuple[str, ...] = ("title", "position", "role", "job")

_HEADING_TAGS: tuple[str, ...] = ("h1", "h2", "h3", "h4", "h5", "h6")
_MIN_BIOGRAPHY_LENGTH = 40

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_PATTERN = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")


@dataclass(frozen=True)
class ExtractedExecutive:
    """One person found on a leadership/about/team page."""

    name: str
    title: str | None
    biography: str | None
    email: str | None
    phone: str | None


def extract_executives(html: str) -> tuple[ExtractedExecutive, ...]:
    """Every person this page's markup identifies, in document order,
    de-duplicated by (name, title).
    """

    soup = BeautifulSoup(html, "html.parser")
    executives: list[ExtractedExecutive] = []
    seen: set[tuple[str, str]] = set()

    for container in _find_person_containers(soup):
        name = _find_name(container)
        if not name:
            continue
        title = _find_title(container, exclude_text=name)
        key = (name.strip().lower(), (title or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)

        exclude_texts = {name, title} if title else {name}
        executives.append(
            ExtractedExecutive(
                name=name,
                title=title,
                biography=_find_biography(container, exclude_texts),
                email=_find_email(container),
                phone=_find_phone(container),
            )
        )

    return tuple(executives)


def _class_and_id(tag: Tag) -> str:
    classes: list[str] = [str(value) for value in (tag.get("class") or [])]
    tag_id = str(tag.get("id") or "")
    return " ".join([*classes, tag_id]).lower()


def _matches_any(tag: Tag, hints: tuple[str, ...]) -> bool:
    haystack = _class_and_id(tag)
    return any(hint in haystack for hint in hints)


def _find_person_containers(soup: BeautifulSoup) -> list[Tag]:
    """The innermost (leaf-most) elements matching CONTAINER_HINTS.

    "Innermost" matters because a page's outer wrapper (e.g. `<section
    class="team">`) commonly also matches, and would otherwise be treated
    as one giant container holding every person on the page instead of one
    container per person.
    """

    matches = [tag for tag in soup.find_all(True) if _matches_any(tag, CONTAINER_HINTS)]
    match_ids = {id(tag) for tag in matches}
    return [
        tag
        for tag in matches
        if not any(id(descendant) in match_ids for descendant in tag.find_all(True))
    ]


def _find_name(container: Tag) -> str | None:
    heading = container.find(_HEADING_TAGS)
    if isinstance(heading, Tag):
        text = heading.get_text(" ", strip=True)
        if text:
            return text

    for tag in container.find_all(True):
        if "name" in _class_and_id(tag):
            text = tag.get_text(" ", strip=True)
            if text:
                return text

    return None


def _find_title(container: Tag, exclude_text: str) -> str | None:
    for tag in container.find_all(True):
        if _matches_any(tag, TITLE_HINTS):
            text = tag.get_text(" ", strip=True)
            if text and text != exclude_text:
                return text
    return None


def _find_biography(container: Tag, exclude_texts: set[str]) -> str | None:
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    candidates = [
        text
        for text in paragraphs
        if text and text not in exclude_texts and len(text) >= _MIN_BIOGRAPHY_LENGTH
    ]
    if not candidates:
        return None
    return max(candidates, key=len)


def _find_email(container: Tag) -> str | None:
    mailto = container.find(
        "a", href=lambda href: bool(href) and href.lower().startswith("mailto:")
    )
    if isinstance(mailto, Tag):
        href = str(mailto["href"])
        return href[len("mailto:") :].split("?", 1)[0].strip() or None

    match = _EMAIL_PATTERN.search(container.get_text(" ", strip=True))
    return match.group(0) if match else None


def _find_phone(container: Tag) -> str | None:
    tel = container.find(
        "a", href=lambda href: bool(href) and href.lower().startswith("tel:")
    )
    if isinstance(tel, Tag):
        href = str(tel["href"])
        value = href[len("tel:") :].strip()
        return value or None

    match = _PHONE_PATTERN.search(container.get_text(" ", strip=True))
    return match.group(0).strip() if match else None
