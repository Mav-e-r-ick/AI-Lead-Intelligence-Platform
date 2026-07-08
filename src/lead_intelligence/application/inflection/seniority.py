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
"""

from __future__ import annotations

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
    ("chief", 12),
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
