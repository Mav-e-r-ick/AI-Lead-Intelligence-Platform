"""Source-agnostic error vocabulary for the Enrichment Provider Framework.

WHY THIS FILE EXISTS:
Mirrors cleaning_exceptions.py / identity_resolution_exceptions.py's role:
a small, shared vocabulary raised by the Enrichment framework's own
classes, so callers never need to know which specific provider or
configuration step caused a failure. A single misbehaving provider raising
an unexpected exception is deliberately NOT one of these — the coordinator
catches that itself and records it as a failed EnrichmentResponse (see
coordinator.py), so one bad provider never sinks a run.
"""


class LeadEnrichmentError(Exception):
    """Base class for every error the Enrichment framework can raise."""


class InvalidEnrichmentConfigurationError(LeadEnrichmentError):
    """Raised when an EnrichmentProfile or ProviderConfiguration is invalid
    or self-contradictory (e.g. a negative timeout, a negative refresh
    max_age). Raised before any provider is executed.
    """


class DuplicateProviderError(LeadEnrichmentError):
    """Raised when two providers registered with a ProviderRegistry report
    the same `provider_id` — provider ids must be unique so the registry,
    the profile's per-provider configuration, and the health tracker can
    all agree on which provider a given id refers to.
    """
