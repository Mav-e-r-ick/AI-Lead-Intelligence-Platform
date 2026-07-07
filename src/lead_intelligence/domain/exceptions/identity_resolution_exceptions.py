"""Source-agnostic error vocabulary for the Identity Resolution Engine.

WHY THIS FILE EXISTS:
Mirrors cleaning_exceptions.py's role for the Cleaning Engine: a small,
shared vocabulary raised by the Identity Resolution Engine's own classes,
so callers never need to know which specific scoring or extraction step
caused a failure.
"""


class LeadIdentityResolutionError(Exception):
    """Base class for every error the Identity Resolution Engine can raise."""


class InvalidIdentityResolutionConfigurationError(LeadIdentityResolutionError):
    """Raised when an IdentityResolutionProfile itself is invalid or
    self-contradictory (e.g. thresholds out of order, a weight outside
    [0.0, 1.0], a signal type referenced with no definition). Raised before
    any record is processed — a broken profile means the run's premises
    are wrong, not that one record is odd.
    """
