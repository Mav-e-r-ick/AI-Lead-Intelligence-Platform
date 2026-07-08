"""Source-agnostic error vocabulary for the Executive Comparison Engine.

WHY THIS FILE EXISTS:
Mirrors cleaning_exceptions.py / identity_resolution_exceptions.py /
enrichment_exceptions.py's role: a small, shared vocabulary raised by the
Comparison Engine's own classes, so callers never need to know which
specific rule or field caused a failure.
"""


class LeadComparisonError(Exception):
    """Base class for every error the Executive Comparison Engine can raise."""


class InvalidComparisonConfigurationError(LeadComparisonError):
    """Raised when a ComparisonProfile itself is invalid or self-
    contradictory (e.g. two rules for the same field, a fuzzy threshold
    outside [0.0, 1.0], no field rules at all). Raised before any field is
    compared — a broken profile means the run's premises are wrong, not
    that one field is odd.
    """
