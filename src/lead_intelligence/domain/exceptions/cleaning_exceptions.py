"""Source-agnostic error vocabulary for the Cleaning Engine.

WHY THIS FILE EXISTS:
Mirrors import_exceptions.py's role for the Import Engine: a small, shared
vocabulary raised by the Cleaning Engine's own classes, so callers never
need to know which specific rule or reference-data file caused a failure.
"""


class LeadCleaningError(Exception):
    """Base class for every error the Cleaning Engine can raise."""


class InvalidCleaningConfigurationError(LeadCleaningError):
    """Raised when a CleaningProfile itself is invalid or self-contradictory.

    Examples: a Business rule that requires an explicit parameter (e.g. a
    default phone region) is enabled without one configured; two mutually
    exclusive rules are enabled simultaneously. This must be raised before
    any record is processed — a broken profile means the run's premises are
    wrong, not that one row is odd (see RuleExecutionError for that case).
    """


class RuleExecutionError(LeadCleaningError):
    """Wraps an unexpected exception raised by a rule's apply() method.

    Raised internally by CleaningPipeline, caught immediately, and recorded
    as a RuleExecutionFailure on the affected record — never propagated to
    the caller. One rule misbehaving on one record must not abort a batch.
    """
