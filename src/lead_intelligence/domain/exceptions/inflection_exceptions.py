"""Source-agnostic error vocabulary for the Inflection Detection Engine.

WHY THIS FILE EXISTS:
Mirrors cleaning_exceptions.py / identity_resolution_exceptions.py /
enrichment_exceptions.py / comparison_exceptions.py's role: a small,
shared vocabulary raised by the Inflection Detection Engine's own
classes, so callers never need to know which specific rule caused a
failure.
"""


class LeadInflectionError(Exception):
    """Base class for every error the Inflection Detection Engine can raise."""


class InvalidInflectionConfigurationError(LeadInflectionError):
    """Raised when an InflectionProfile itself is invalid or self-
    contradictory (e.g. an out-of-range confidence override). Raised
    before any rule is evaluated.
    """


class DuplicateInflectionRuleError(LeadInflectionError):
    """Raised when two rules registered with an InflectionRuleRegistry
    report the same `rule_id` — rule ids must be unique so the registry
    and profile overrides can unambiguously agree on which rule an id
    refers to.
    """
