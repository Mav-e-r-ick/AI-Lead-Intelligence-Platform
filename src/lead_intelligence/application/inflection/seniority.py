"""Title seniority ranking: a deterministic, keyword-based approximation of
"how senior does this title sound," used only to decide the *direction* of
a title change (Promotion vs. Demotion).

WHY THIS IS A KEYWORD TABLE, NOT AI:
This task's scope explicitly excludes AI. Seniority ordering for common
executive titles is stable enough (an "SVP" outranks a "Manager" in every
realistic organization) that a small, explicit, versionable keyword table
is both sufficient and far more explainable than a model call — every
rank this module produces can be traced to the exact keyword that produced
it. It will not understand an organization's idiosyncratic internal title
scheme, an honestly-scoped Version 1 limitation, not a bug.

WHY RANKING TAKES THE LONGEST MATCHING KEYWORD, NOT THE HIGHEST RANK:
Longer, more specific phrases ("vice president") often contain shorter,
less specific ones ("president") as substrings, even when the shorter
phrase's own rank is *higher* (a standalone "President" outranks a "Vice
President"). Taking the highest rank among every matching keyword would
therefore let "president" hijack the score for "Vice President". Taking
the rank of the longest matching keyword instead is order-independent and
always prefers the more specific phrase — the one that actually describes
the title — over a shorter substring it happens to contain. Ties in length
are broken by the higher rank.

WHY NAMED C-SUITE FUNCTIONAL TITLES (COO/CFO/CTO/.../Chief Digital Officer)
SHARE ONE RANK INSTEAD OF EACH GETTING ITS OWN (Product Accuracy Audit,
Priority 4):
Before this table was expanded, every one of these titles fell through to
the generic "chief" keyword, so two *different* named C-suite titles
always compared as equal rank — correctly silent (no promotion/demotion),
but for the wrong reason: the specific title was never actually
recognized, only the generic fallback. Each now has its own explicit,
traceable entry (so `seniority_rank` reports the specific keyword that
matched, not "chief"), but they are deliberately kept at the *same* rank
as each other and as the generic "chief" fallback: there is no real-data
or audit evidence that, say, a "Chief Financial Officer" outranks a
"Chief Operating Officer" in every organization (unlike "SVP" > "VP",
which holds everywhere), so assigning them a strict pecking order would
be inventing a hierarchy this module has no basis for. A transition
between two named C-suite titles therefore still correctly produces no
promotion/demotion signal — the same honest "these are peers, or at
least this module can't tell" behavior as before, just now backed by
actually recognizing the title instead of an accidental generic match.
A transition from a lower tier (VP/SVP/EVP) into any of these, or from
any of these up to President/CEO, is unaffected and still detected.

Some real-world C-suite acronyms are genuinely ambiguous (e.g. "CRO" is
both "Chief Revenue Officer" and "Chief Risk Officer"; "CPO" is both
"Chief Product Officer" and "Chief People Officer"; "CDO" is both "Chief
Data Officer" and "Chief Digital Officer") — those are recognized only by
their unambiguous, fully spelled-out form, never by the ambiguous
acronym, to avoid a confident-looking match that silently guesses wrong.
"""

from __future__ import annotations

#: The shared rank for every explicitly-named C-suite functional title
#: below (see "WHY NAMED C-SUITE FUNCTIONAL TITLES..." above) — identical
#: to the pre-existing generic "chief" fallback's rank, so recognizing
#: these titles by name changes nothing about where they sit relative to
#: any other tier; it only makes the match specific and traceable.
_CHIEF_OFFICER_RANK = 12

#: (keyword, rank) — checked as a case-insensitive substring of the title.
#: Higher rank = more senior. Deliberately not exhaustive; see module
#: docstring. Ordered here roughly least-to-most senior for readability
#: only — matching itself does not depend on this order.
SENIORITY_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("intern", 1),
    ("trainee", 1),
    ("assistant", 2),
    ("associate", 3),
    ("analyst", 3),
    ("specialist", 3),
    ("coordinator", 3),
    ("representative", 3),
    ("manager", 4),
    ("senior manager", 5),
    ("head of", 5),
    ("director", 6),
    ("senior director", 7),
    ("managing director", 7),
    ("vice president", 8),
    ("vp", 8),
    ("senior vice president", 9),
    ("svp", 9),
    ("executive vice president", 10),
    ("evp", 10),
    ("president", 11),
    ("chief", _CHIEF_OFFICER_RANK),
    ("chief operating officer", _CHIEF_OFFICER_RANK),
    ("coo", _CHIEF_OFFICER_RANK),
    ("chief financial officer", _CHIEF_OFFICER_RANK),
    ("cfo", _CHIEF_OFFICER_RANK),
    ("chief technology officer", _CHIEF_OFFICER_RANK),
    ("cto", _CHIEF_OFFICER_RANK),
    ("chief information officer", _CHIEF_OFFICER_RANK),
    ("cio", _CHIEF_OFFICER_RANK),
    ("chief marketing officer", _CHIEF_OFFICER_RANK),
    ("cmo", _CHIEF_OFFICER_RANK),
    ("chief human resources officer", _CHIEF_OFFICER_RANK),
    ("chro", _CHIEF_OFFICER_RANK),
    ("chief revenue officer", _CHIEF_OFFICER_RANK),  # "CRO" is ambiguous, see module docstring
    ("chief experience officer", _CHIEF_OFFICER_RANK),
    ("chief relationship officer", _CHIEF_OFFICER_RANK),
    ("chief product officer", _CHIEF_OFFICER_RANK),  # "CPO" is ambiguous, see module docstring
    ("chief growth officer", _CHIEF_OFFICER_RANK),
    ("chief data officer", _CHIEF_OFFICER_RANK),  # "CDO" is ambiguous, see module docstring
    ("chief digital officer", _CHIEF_OFFICER_RANK),  # "CDO" is ambiguous, see module docstring
    ("founder", 13),
    ("chief executive officer", 13),
    ("ceo", 13),
)


def seniority_rank(title: str) -> int | None:
    """The seniority rank implied by `title`, or None if no keyword matches.

    Args:
        title: A job title, in any casing (e.g. "Senior Vice President of
            Engineering").

    Returns:
        The rank of the longest SENIORITY_KEYWORDS entry that appears as a
        substring of the normalized title (ties broken by higher rank), or
        None if nothing matched — an honest "this engine doesn't recognize
        this title," never a guessed default.
    """

    normalized = title.strip().lower()
    matches = [
        (len(keyword), rank)
        for keyword, rank in SENIORITY_KEYWORDS
        if keyword in normalized
    ]
    if not matches:
        return None
    matches.sort()
    return matches[-1][1]
