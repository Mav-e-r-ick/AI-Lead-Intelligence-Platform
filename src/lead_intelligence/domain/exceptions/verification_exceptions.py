"""Source-agnostic error vocabulary for the Contact Verification Framework.

WHY THIS FILE EXISTS:
Mirrors enrichment_exceptions.py's role: a small, shared vocabulary raised
by the Verification framework's own classes, so callers never need to know
which specific provider or configuration step caused a failure. A single
misbehaving provider raising an unexpected exception is deliberately NOT
one of these — the coordinator catches that itself and records it as a
failed VerificationResult (see coordinator.py), so one bad provider never
sinks a run.
"""


class LeadVerificationError(Exception):
    """Base class for every error the Verification framework can raise."""


class InvalidVerificationConfigurationError(LeadVerificationError):
    """Raised when a VerificationProfile or VerificationProviderConfiguration
    is invalid or self-contradictory (e.g. a non-positive timeout). Raised
    before any provider is executed.
    """


class DuplicateVerificationProviderError(LeadVerificationError):
    """Raised when two providers registered with a VerificationCoordinator
    report the same `provider_id` — provider ids must be unique so the
    coordinator and the profile's per-provider configuration can agree on
    which provider a given id refers to.
    """
