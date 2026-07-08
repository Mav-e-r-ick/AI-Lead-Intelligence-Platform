"""Source-agnostic error vocabulary for the Search Layer.

WHY THIS FILE EXISTS:
Mirrors enrichment_exceptions.py / verification_exceptions.py's role: a
small, shared vocabulary raised by the Search Layer's own classes, so
callers never need to know which specific provider or configuration step
caused a failure. A single misbehaving search provider raising an
unexpected exception is deliberately NOT one of these — the coordinator
catches that itself and records it as a failed SearchResponse (see
coordinator.py), so one bad provider never sinks a run.
"""


class LeadSearchError(Exception):
    """Base class for every error the Search Layer can raise."""


class InvalidSearchConfigurationError(LeadSearchError):
    """Raised when a SearchProfile or SearchProviderConfiguration is
    invalid or self-contradictory (e.g. a non-positive timeout). Raised
    before any provider is executed.
    """


class DuplicateSearchProviderError(LeadSearchError):
    """Raised when two providers registered with a SearchProviderRegistry
    report the same `provider_id` — provider ids must be unique so the
    registry and the profile's per-provider configuration can agree on
    which provider a given id refers to.
    """
