"""Rule-based extraction of (executive name, title, company) from a
page's title and visible text — deterministic regex patterns over common
press-release phrasings, per Version 1's explicit "no AI, no LLM"
constraint.

This is the "Observation Extraction" stage's fact-finding half; turning
found facts into ObservationCandidates is engine.py's job.

WHY A SMALL, NAMED SET OF PATTERNS INSTEAD OF ANYTHING SMARTER:
Every pattern below matches one specific, widely-used announcement
phrasing ("X has been appointed Y of Z", "X joins Z as Y", ...). This is
the honest deterministic floor: a page that phrases its announcement
differently simply yields no facts (and the engine still records the page
itself as evidence) — it never yields *guessed* facts. Each pattern has a
stable id, carried onto the result as `matched_pattern`, so any extracted
fact is traceable to exactly the rule that produced it.

KNOWN, ACCEPTED VERSION 1 LIMITATIONS (documented, not bugs):
- Names are recognized as 2–4 consecutive capitalized words; a
  capitalized phrase immediately preceding a real name (e.g. "Officer
  John Smith") can over-capture into the name. Lowercase particles
  ("van", "de") in the middle of a name are not recognized.
- The first match wins, scanning the page title first, then the visible
  text — one page yields at most one (name, title, company) fact set.
- English phrasings only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: 2–4 consecutive capitalized words (letters, apostrophes, periods,
#: hyphens) — the shape of a person's name in announcement prose.
_NAME = r"[A-Z][a-zA-Z'.\-]+(?:\s+[A-Z][a-zA-Z'.\-]+){1,3}"

#: A job title: starts capitalized, then letters/digits/spaces/&/slashes/
#: hyphens, non-greedy so it stops at the following anchor word.
_ROLE = r"[A-Z][A-Za-z0-9&/\- ]{1,60}?"

#: A company name: starts capitalized, then a permissive character class,
#: non-greedy up to the sentence boundary the pattern anchors on.
_COMPANY = r"[A-Z][\w&.,'()\- ]{1,80}?"

#: Where a trailing role/company capture must stop: sentence punctuation,
#: a newline, or end of input.
_BOUNDARY = r"(?=[.,;:!?\n]|$)"


@dataclass(frozen=True)
class ExtractedFacts:
    """The (name, title, company) facts one page's prose yielded — any
    field None when the matched pattern (or the page) didn't provide it.

    Attributes:
        full_name: The executive's name, as written on the page.
        title: The executive's job title, as written on the page.
        company_name: The company, as written on the page.
        matched_pattern: The id of the pattern that produced these facts,
            or None when nothing matched (in which case every other field
            is also None).
    """

    full_name: str | None
    title: str | None
    company_name: str | None
    matched_pattern: str | None


NO_FACTS = ExtractedFacts(
    full_name=None, title=None, company_name=None, matched_pattern=None
)

#: (pattern_id, compiled_pattern), tried in order — most specific (full
#: name+role+company triples) first. Group names: name / role / company.
FACT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "FACT-001-appointed-role-of-company",
        re.compile(
            # The auxiliary verb is optional so headline phrasings
            # ("Ada Lovelace named CTO of Acme Corp") match, not just
            # body-prose ones ("... has been appointed ...").
            rf"(?P<name>{_NAME})\s+(?:(?:has been|was|is|will be)\s+)?"
            rf"(?:appointed|named)\s+(?:as\s+)?(?:its\s+|the\s+)?"
            rf"(?P<role>{_ROLE})\s+(?:of|at)\s+(?P<company>{_COMPANY}){_BOUNDARY}"
        ),
    ),
    (
        "FACT-002-promoted-to-role-of-company",
        re.compile(
            rf"(?P<name>{_NAME})\s+(?:has been|was|is)\s+promoted\s+to\s+"
            rf"(?:the\s+role\s+of\s+)?"
            rf"(?P<role>{_ROLE})\s+(?:of|at)\s+(?P<company>{_COMPANY}){_BOUNDARY}"
        ),
    ),
    (
        "FACT-003-joins-company-as-role",
        re.compile(
            rf"(?P<name>{_NAME})\s+(?:joins|has joined|joined)\s+"
            rf"(?P<company>{_COMPANY})\s+as\s+(?:its\s+|the\s+)?"
            rf"(?P<role>{_ROLE}){_BOUNDARY}"
        ),
    ),
    (
        "FACT-004-name-comma-role-of-company",
        re.compile(
            rf"(?P<name>{_NAME}),\s+(?P<role>{_ROLE})\s+(?:of|at)\s+"
            rf"(?P<company>{_COMPANY}){_BOUNDARY}"
        ),
    ),
    (
        "FACT-005-promoted-to-role",
        re.compile(
            rf"(?P<name>{_NAME})\s+(?:has been|was|is)\s+promoted\s+to\s+"
            rf"(?P<role>{_ROLE}){_BOUNDARY}"
        ),
    ),
)


def extract_facts(title: str, visible_text: str) -> ExtractedFacts:
    """Extract one (name, title, company) fact set from a page's prose.

    Args:
        title: The page's title — scanned first, because announcement
            headlines are denser and less noisy than body text.
        visible_text: The page's visible text, scanned only if the title
            yielded nothing.

    Returns:
        The first pattern match found (title first, then text; patterns
        tried in FACT_PATTERNS order within each), or NO_FACTS if no
        pattern matched anywhere.
    """

    for source_text in (title, visible_text):
        if not source_text:
            continue
        for pattern_id, pattern in FACT_PATTERNS:
            match = pattern.search(source_text)
            if match is None:
                continue
            groups = match.groupdict()
            return ExtractedFacts(
                full_name=_clean(groups.get("name")),
                title=_clean(groups.get("role")),
                company_name=_clean(groups.get("company")),
                matched_pattern=pattern_id,
            )

    return NO_FACTS


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip(",")
    return cleaned or None
