"""Rule-based extraction of (executive name, title, company) from a
page's title and visible text — deterministic regex patterns over common
press-release phrasings, per Version 1's explicit "no AI, no LLM"
constraint. Also independently extracts an email, phone number, and
LinkedIn profile URL from the page's visible text, since a leadership/
team page (CompanyCrawlerProvider's typical target — a bio "card" with a
mailto:/tel: link and a LinkedIn icon) rarely phrases things as one of
the announcement patterns below at all.

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

WHY email/phone/linkedin_url ARE NOT GATED ON A NAME/TITLE/COMPANY MATCH:
The five patterns below all describe *announcement prose* ("X was named Y
of Z") — a different shape of text than a leadership-page bio card ("John
Smith, CEO · jsmith@acme.com · linkedin.com/in/johnsmith"), which usually
matches none of them. Requiring an announcement-pattern match first would
silently drop real, plainly-present contact facts on exactly the page
type CompanyCrawlerProvider spends most of its time on. These three are
therefore extracted independently, via their own regex, from the same
visible text — same "no AI, deterministic pattern" floor, just not
coupled to whether an announcement sentence also happened to be present.

KNOWN, ACCEPTED VERSION 1 LIMITATIONS (documented, not bugs):
- Names are recognized as 2–4 consecutive capitalized words; a
  capitalized phrase immediately preceding a real name (e.g. "Officer
  John Smith") can over-capture into the name. Lowercase particles
  ("van", "de") in the middle of a name are not recognized.
- The first match wins, scanning the page title first, then the visible
  text — one page yields at most one (name, title, company) fact set.
- English phrasings only.
- Exactly one email/phone/LinkedIn URL is reported per page (the first
  found) — a page listing many people's individual contact details is a
  Version 1 known gap, matching CompanyWebsiteProvider's own
  per-container (not per-page) extraction being the richer tool for that
  case.
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

#: Same pattern CompanyWebsiteProvider's own extraction.py uses (see that
#: module) — one shared, proven regex vocabulary for these two fields
#: rather than a second, drifting copy.
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_PATTERN = re.compile(r"(\+?\d[\d\-.\s()]{7,}\d)")

#: A LinkedIn person or company profile URL, with or without a country
#: subdomain (e.g. "uk.linkedin.com") or trailing slash.
_LINKEDIN_PATTERN = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/(?:in|company)/[A-Za-z0-9\-_%]+/?"
)


@dataclass(frozen=True)
class ExtractedFacts:
    """The facts one page's prose yielded — any field None when nothing
    on the page provided it.

    Attributes:
        full_name: The executive's name, from one of FACT_PATTERNS below.
        title: The executive's job title, from one of FACT_PATTERNS.
        company_name: The company, from one of FACT_PATTERNS.
        matched_pattern: The id of the FACT_PATTERNS entry that produced
            (full_name, title, company_name), or None when none matched
            (in which case those three fields are also None) — see module
            docstring for why email/phone/linkedin_url are independent of
            this.
        email: The first email address found in the page's visible text
            (mailto: links are not specially handled here — this operates
            on plain text, unlike CompanyWebsiteProvider's DOM-aware
            extraction), or None.
        phone: The first phone number found, or None.
        linkedin_url: The first LinkedIn profile URL found, or None.
    """

    full_name: str | None
    title: str | None
    company_name: str | None
    matched_pattern: str | None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None


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
    """Extract one (name, title, company) announcement fact set, plus an
    independently-found email/phone/LinkedIn URL, from a page's prose.

    Args:
        title: The page's title — scanned first for the announcement
            patterns, because announcement headlines are denser and less
            noisy than body text.
        visible_text: The page's visible text — scanned for the
            announcement patterns only if the title yielded nothing;
            always scanned for email/phone/linkedin_url (see module
            docstring for why those aren't gated on a pattern match).

    Returns:
        An ExtractedFacts combining the first announcement-pattern match
        found (title first, then text; patterns tried in FACT_PATTERNS
        order within each — full_name/title/company_name/matched_pattern
        all None if nothing matched) with whatever email/phone/
        linkedin_url the visible text independently contains.
    """

    name_facts = NO_FACTS
    for source_text in (title, visible_text):
        if not source_text:
            continue
        for pattern_id, pattern in FACT_PATTERNS:
            match = pattern.search(source_text)
            if match is None:
                continue
            groups = match.groupdict()
            name_facts = ExtractedFacts(
                full_name=_clean(groups.get("name")),
                title=_clean(groups.get("role")),
                company_name=_clean(groups.get("company")),
                matched_pattern=pattern_id,
            )
            break
        if name_facts is not NO_FACTS:
            break

    email_match = _EMAIL_PATTERN.search(visible_text) if visible_text else None
    phone_match = _PHONE_PATTERN.search(visible_text) if visible_text else None
    linkedin_match = _LINKEDIN_PATTERN.search(visible_text) if visible_text else None

    return ExtractedFacts(
        full_name=name_facts.full_name,
        title=name_facts.title,
        company_name=name_facts.company_name,
        matched_pattern=name_facts.matched_pattern,
        email=email_match.group(0) if email_match else None,
        phone=phone_match.group(0).strip() if phone_match else None,
        linkedin_url=linkedin_match.group(0) if linkedin_match else None,
    )


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip(",")
    return cleaned or None
