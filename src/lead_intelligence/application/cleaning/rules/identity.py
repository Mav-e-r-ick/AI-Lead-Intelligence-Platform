"""Identity category rules: CLN-001 through CLN-010.

Fields: First Name, Last Name, Title, Contact Level, Job Function.
See docs/CLEANING_RULES.md §9.1 for the full specification each rule below
implements.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from lead_intelligence.application.cleaning import field_contract as F
from lead_intelligence.application.cleaning.reference_data.acronyms import (
    DEFAULT_ACRONYMS,
)
from lead_intelligence.application.cleaning.reference_data.name_particles import (
    CAPITALIZED_NAME_PREFIXES,
    DEFAULT_LOWERCASE_PARTICLES,
)
from lead_intelligence.application.cleaning.rules.common import (
    IdenticalFieldsWarningRule,
    MissingFieldWarningRuleSet,
    RegexShapeWarningRule,
    ThresholdWarningRule,
    WhitespaceNormalizationRule,
)
from lead_intelligence.application.dto.cleaning_models import QualityWarningDraft
from lead_intelligence.application.ports.cleaning_rule_port import (
    NormalizationRule,
    QualityCheckRule,
    RuleCategory,
    RuleMetadata,
    RuleStage,
)

_CATEGORY = RuleCategory.IDENTITY


def _case_name_token(
    token: str, particles: frozenset[str], prefixes: tuple[str, ...]
) -> str:
    if not token:
        return token
    lower = token.lower()
    if lower in particles:
        return lower
    for prefix in prefixes:
        if lower.startswith(prefix) and len(lower) > len(prefix):
            rest = lower[len(prefix) :]
            head = (
                prefix[:-1].capitalize() + "'"
                if prefix.endswith("'")
                else prefix.capitalize()
            )
            return head + rest.capitalize()
    return token.capitalize()


def _standardize_name_casing(
    value: str, particles: frozenset[str], prefixes: tuple[str, ...]
) -> str:
    words = value.split(" ")
    cased_words = []
    for word in words:
        parts = word.split("-")
        cased_words.append(
            "-".join(_case_name_token(p, particles, prefixes) for p in parts)
        )
    return " ".join(cased_words)


class NameCasingStandardizationRule(NormalizationRule):
    """CLN-002 — Name Casing Standardization."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-002",
            name="Name Casing Standardization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.FIRST_NAME, F.LAST_NAME),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        particles = frozenset(params.get("particles", DEFAULT_LOWERCASE_PARTICLES))
        prefixes = tuple(params.get("prefixes", CAPITALIZED_NAME_PREFIXES))
        changes: dict[str, Any] = {}
        for field_name in self._metadata.fields:
            value = values.get(field_name)
            if isinstance(value, str) and value:
                cased = _standardize_name_casing(value, particles, prefixes)
                if cased != value:
                    changes[field_name] = cased
        return changes


_SUFFIX_PATTERN = re.compile(
    r"\s+(Jr\.?|Sr\.?|I{1,3}|IV|V|Ph\.?D\.?|M\.?D\.?)$", re.IGNORECASE
)


class NameSuffixNormalizationRule(NormalizationRule):
    """CLN-003 — Name Suffix Normalization.

    Off by default. When enabled with parameters["strip"]=True, detaches a
    trailing suffix from Last Name into a derived `name_suffix` attribute
    rather than deleting it.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-003",
            name="Name Suffix Normalization",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.LAST_NAME,),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        if not params.get("strip", False):
            return {}
        value = values.get(F.LAST_NAME)
        if not isinstance(value, str):
            return {}
        match = _SUFFIX_PATTERN.search(value)
        if not match:
            return {}
        suffix = match.group(1)
        new_last_name = _SUFFIX_PATTERN.sub("", value).strip()
        return {F.LAST_NAME: new_last_name, F.NAME_SUFFIX: suffix}


class TitleAcronymCasingRule(NormalizationRule):
    """CLN-004 — Title Acronym Casing Correction."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-004",
            name="Title Acronym Casing Correction",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.TITLE,),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        acronyms = {**DEFAULT_ACRONYMS, **params.get("acronyms", {})}
        value = values.get(F.TITLE)
        if not isinstance(value, str) or not value:
            return {}
        tokens = re.split(r"(\s+|[,/-])", value)
        changed = False
        new_tokens: list[str] = []
        for token in tokens:
            replacement = acronyms.get(token.lower())
            if replacement is not None:
                new_tokens.append(replacement)
                changed = True
            else:
                new_tokens.append(token)
        return {F.TITLE: "".join(new_tokens)} if changed else {}


_DEFAULT_EXPANSION_MAP: dict[str, str] = {
    "sr.": "Senior",
    "sr": "Senior",
    "jr.": "Junior",
    "jr": "Junior",
    "vp": "Vice President",
}


class TitleAbbreviationRule(NormalizationRule):
    """CLN-005 — Title Abbreviation Expansion/Contraction."""

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-005",
            name="Title Abbreviation Expansion/Contraction",
            category=_CATEGORY,
            stage=RuleStage.BUSINESS,
            fields=(F.TITLE,),
            configurable=True,
            default_enabled=False,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(self, values: Mapping[str, Any], profile: Any) -> Mapping[str, Any]:
        params = profile.parameters_for(self._metadata.rule_id)
        direction = params.get("direction", "expand")
        if direction == "expand":
            mapping = params.get("mapping", _DEFAULT_EXPANSION_MAP)
        else:
            mapping = params.get(
                "mapping", {v.lower(): k for k, v in _DEFAULT_EXPANSION_MAP.items()}
            )
        value = values.get(F.TITLE)
        if not isinstance(value, str) or not value:
            return {}
        tokens = re.split(r"(\s+)", value)
        changed = False
        new_tokens: list[str] = []
        for token in tokens:
            replacement = mapping.get(token.lower())
            if replacement is not None:
                new_tokens.append(replacement)
                changed = True
            else:
                new_tokens.append(token)
        return {F.TITLE: "".join(new_tokens)} if changed else {}


_LEVEL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "c-level": ("chief", "ceo", "cfo", "coo", "cto", "cio", "cmo"),
    "board of directors": ("board", "director"),
    "executive vice presidents": ("executive vice president", "evp"),
    "senior vice presidents": ("senior vice president", "svp"),
    "vice presidents": ("vice president", "vp"),
}


class ContactLevelTitleConsistencyWarningRule(QualityCheckRule):
    """CLN-010 — Contact Level / Title Inconsistency Warning.

    A low-confidence heuristic; explicitly labeled as such in the message.
    """

    def __init__(self) -> None:
        self._metadata = RuleMetadata(
            rule_id="CLN-010",
            name="Contact Level / Title Inconsistency Warning",
            category=_CATEGORY,
            stage=RuleStage.WARNING,
            fields=(F.CONTACT_LEVEL, F.TITLE),
            configurable=True,
            default_enabled=True,
        )

    @property
    def metadata(self) -> RuleMetadata:
        return self._metadata

    def apply(
        self, values: Mapping[str, Any], profile: Any
    ) -> list[QualityWarningDraft]:
        contact_level = values.get(F.CONTACT_LEVEL)
        title = values.get(F.TITLE)
        if (
            not isinstance(contact_level, str)
            or not contact_level
            or not isinstance(title, str)
        ):
            return []
        title_lower = title.lower()
        contact_level_lower = contact_level.lower()
        for level_key, keywords in _LEVEL_KEYWORDS.items():
            if level_key in contact_level_lower:
                if any(keyword in title_lower for keyword in keywords):
                    return []
                return [
                    QualityWarningDraft(
                        code="CONTACT_LEVEL_TITLE_MISMATCH",
                        message=(
                            f"Contact Level '{contact_level}' but Title '{title}' has no "
                            "matching keyword (heuristic, low-confidence)."
                        ),
                        field_names=(F.CONTACT_LEVEL, F.TITLE),
                    )
                ]
        return []


IDENTITY_RULES: tuple[NormalizationRule | QualityCheckRule, ...] = (
    WhitespaceNormalizationRule(
        "CLN-001",
        "Trim & Normalize Whitespace (Identity Fields)",
        _CATEGORY,
        (F.FIRST_NAME, F.LAST_NAME, F.TITLE, F.CONTACT_LEVEL, F.JOB_FUNCTION),
    ),
    NameCasingStandardizationRule(),
    NameSuffixNormalizationRule(),
    TitleAcronymCasingRule(),
    TitleAbbreviationRule(),
    MissingFieldWarningRuleSet(
        "CLN-006",
        "Missing Name Warning",
        _CATEGORY,
        (
            (F.FIRST_NAME, "MISSING_FIRST_NAME", "First Name is missing."),
            (F.LAST_NAME, "MISSING_LAST_NAME", "Last Name is missing."),
        ),
    ),
    IdenticalFieldsWarningRule(
        "CLN-007",
        "Identical First/Last Name Warning",
        _CATEGORY,
        (F.FIRST_NAME,),
        F.LAST_NAME,
        "IDENTICAL_FIRST_LAST_NAME",
        "First Name and Last Name are identical.",
    ),
    RegexShapeWarningRule(
        "CLN-008",
        "Name Contains Unexpected Characters Warning",
        _CATEGORY,
        (F.FIRST_NAME, F.LAST_NAME),
        re.compile(r"[^A-Za-z\s\-'À-ɏ]"),
        False,
        "UNEXPECTED_CHARACTERS_IN_NAME",
        "Name field contains characters outside the expected allow-list.",
    ),
    ThresholdWarningRule(
        "CLN-009",
        "Title Unusually Long Warning",
        _CATEGORY,
        F.TITLE,
        100,
        "gt",
        "TITLE_UNUSUALLY_LONG",
        "Title is {length} characters, exceeding the {threshold}-character threshold.",
    ),
    ContactLevelTitleConsistencyWarningRule(),
)
