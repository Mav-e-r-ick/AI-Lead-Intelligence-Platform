"""EnrichmentProviderPort: the one contract every enrichment source must
implement, whatever it actually is (a web scraper, a commercial API
client, a CRM adapter, or — in tests — an in-memory fake).

WHY THIS INTERFACE HAS NO DEFAULT METHODS OR HELPER LOGIC:
This task's explicit scope is "provider interface only — no provider-
specific business logic." Any shared behavior a real provider might want
(HTTP retries, rate-limit backoff, HTML parsing) belongs in that concrete
provider's own infrastructure code, never here — this file must stay
honestly empty of anything except the shape every provider agrees to.

WHY fetch() TAKES AND RETURNS PLAIN DTOs, NOT A DIGITAL TWIN:
domain/entities/ does not exist yet. A provider is handed an
EnrichmentRequest (subject_type, subject_id, known_attributes) and must
hand back an EnrichmentResponse — it never needs to know what a Digital
Twin actually is, only what it's being asked to look up. This keeps the
port implementable today and unaffected once the Digital Twin entity is
eventually built.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    SubjectType,
)


class EnrichmentProviderPort(ABC):
    """One external (or future-external) source of executive information."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """A short, stable, unique identifier (e.g. "company_website",
        "dnb", "news"). Used as the key everywhere a provider is
        referenced: ProviderRegistry, EnrichmentProfile's per-provider
        configuration, and ProviderHealthTracker."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """A human-readable name, for logs and future admin UIs."""

    @property
    @abstractmethod
    def supported_subject_types(self) -> frozenset[SubjectType]:
        """Which Subject type(s) this provider can be asked about. A
        Leadership Page provider might support only Person; a D&B
        provider might support only Company. ProviderRegistry uses this to
        exclude a provider from consideration entirely for the wrong
        subject_type, before enabled/health/refresh checks ever run."""

    @abstractmethod
    def fetch(self, request: EnrichmentRequest) -> EnrichmentResponse:
        """Attempt to fulfill `request` and return the result.

        Implementations should not raise for ordinary "found nothing" or
        "source unavailable" cases — report those via
        `EnrichmentResponse.status`/`error_message` instead, so the
        coordinator's per-provider metrics and health tracking stay
        accurate. An actual raised exception is still handled safely (the
        coordinator treats it as a failure and keeps going), but it should
        be reserved for genuinely unexpected programming errors, not
        expected real-world outcomes like "no news articles found."
        """
