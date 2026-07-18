"""generate_message: turns one detected Inflection into a short,
contextual outreach message — the pipeline's final stage (Executive ->
Search -> Extract -> Identity Match -> Compare -> Detect Inflection ->
Update Database -> Generate Message).

No AI, no LLM: one named template per InflectionType, the same
deterministic, explainable floor every other stage in this platform
already uses. A human still reviews and sends the message; this only
drafts it.
"""

from __future__ import annotations

from lead_intelligence.application.dto.inflection_models import (
    Inflection,
    InflectionReport,
    InflectionType,
)

#: One template per InflectionType. `{name}`/`{company}`/`{title}` are
#: always available (resolve_* functions fall back to a generic phrase
#: when the field itself is unknown, never leaving a raw "None" in the
#: message); `{previous_title}`/`{previous_company}` are only referenced
#: by the two templates that actually have a "before" value to mention.
_TEMPLATES: dict[InflectionType, str] = {
    InflectionType.PROMOTION: (
        "Hi {name}, congratulations on your promotion to {title} at "
        "{company}! Would love to reconnect and hear more about your "
        "new role."
    ),
    InflectionType.DEMOTION: (
        "Hi {name}, I noticed a change in your role at {company} — now "
        "{title}. Wanted to check in and see how things are going."
    ),
    InflectionType.COMPANY_CHANGE: (
        "Hi {name}, congratulations on your new role as {title} at "
        "{company}! Would love to reconnect now that you're there."
    ),
    InflectionType.POSSIBLE_RESIGNATION: (
        "Hi {name}, I wanted to check in — I couldn't confirm your "
        "current title at {company}. Let me know if anything's changed "
        "on your end."
    ),
    InflectionType.CONTACT_INFO_CHANGED: (
        "Hi {name}, I noticed your contact details at {company} have "
        "changed. Wanted to make sure I have the right information to "
        "stay in touch."
    ),
    InflectionType.EXECUTIVE_NEWLY_APPEARED: (
        "Hi {name}, I see you're now {title} at {company} — great to "
        "connect. Would love to learn more about what you're working on."
    ),
    InflectionType.EXECUTIVE_NO_LONGER_FOUND: (
        "Hi {name}, it's been a while since we've been in touch — "
        "wanted to reconnect and see where things stand at {company}."
    ),
}

_UNKNOWN_COMPANY = "your company"
_UNKNOWN_TITLE = "your new role"

#: Used only if a future InflectionType is added without a corresponding
#: template above — never raises, always drafts something reviewable.
_FALLBACK_TEMPLATE = (
    "Hi {name}, I noticed a professional update at {company} and wanted "
    "to reconnect."
)


def generate_message(
    executive_name: str,
    company: str | None,
    title: str | None,
    inflection: Inflection,
) -> str:
    """Draft one contextual outreach message for `inflection`.

    Args:
        executive_name: The executive's resolved name (never blank —
            callers only reach this stage once a name is known).
        company: The executive's current company, or None if unknown.
        title: The executive's current title, or None if unknown.
        inflection: The (usually strongest) detected Inflection to write
            an outreach message about.

    Returns:
        A short, ready-to-review outreach message. Never raises for a
        missing company/title — falls back to a generic phrase instead.
    """

    template = _TEMPLATES.get(inflection.type, _FALLBACK_TEMPLATE)
    return template.format(
        name=executive_name,
        company=company or _UNKNOWN_COMPANY,
        title=title or _UNKNOWN_TITLE,
    )


def generate_message_for_report(
    report: InflectionReport | None,
    executive_name: str,
    company: str | None,
    title: str | None,
) -> str | None:
    """Draft one outreach message for the strongest inflection in
    `report` (the same "strongest wins" convention
    ExecutiveRepository.apply_changes uses for what gets persisted), or
    None if no inflection was detected (a legitimate, common outcome —
    not every executive has news worth reaching out about)."""

    if report is None or not report.inflections:
        return None

    strongest = max(report.inflections, key=lambda inflection: inflection.confidence)
    return generate_message(executive_name, company, title, strongest)
