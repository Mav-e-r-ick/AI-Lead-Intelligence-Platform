"""VerificationProviderPort: the one contract every contact verification
source must implement, whatever it actually is (a commercial email/phone
verification API, or — in tests — an in-memory fake).

WHY THIS INTERFACE HAS NO DEFAULT METHODS OR HELPER LOGIC:
This task's explicit scope is "provider interface only — no provider-
specific business logic, no commercial API integration yet." Any shared
behavior a real provider might want (HTTP retries, auth, rate-limit
backoff) belongs in that concrete provider's own infrastructure code,
never here — this file must stay honestly empty of anything except the
shape every provider agrees to.

WHY EmailVerificationPort AND PhoneVerificationPort EXIST SEPARATELY FROM
VerificationProviderPort:
A future NeverBounce/ZeroBounce/Kickbox/Bouncer adapter only ever verifies
email; a future Twilio Lookup/Numverify/Abstract API adapter only ever
verifies phone numbers. Fixing `supported_contact_types` in these two
narrower base classes means a concrete provider only has to implement
`provider_id`, `display_name`, and `verify()` — it can never accidentally
claim to support the wrong contact type. VerificationCoordinator still
only depends on the common VerificationProviderPort, so it works
identically regardless of which of the two a given provider is.

WHY verify() TAKES AND RETURNS PLAIN DTOs:
A provider is handed a VerificationRequest (contact_type, value,
subject_id) and must hand back a VerificationResult — it never needs to
know what a Digital Twin actually is, only what it's being asked to check.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationRequest,
    VerificationResult,
)


class VerificationProviderPort(ABC):
    """One external (or future-external) source of contact verification."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """A short, stable, unique identifier (e.g. "neverbounce",
        "twilio_lookup"). Used as the key everywhere a provider is
        referenced: the coordinator's internal registry and
        VerificationProfile's per-provider configuration."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """A human-readable name, for logs and future admin UIs."""

    @property
    @abstractmethod
    def supported_contact_types(self) -> frozenset[ContactType]:
        """Which ContactType(s) this provider can be asked to verify. Used
        to exclude a provider from consideration entirely for the wrong
        contact_type, before the enabled check ever runs."""

    @abstractmethod
    def verify(self, request: VerificationRequest) -> VerificationResult:
        """Attempt to fulfill `request` and return the result.

        Implementations should not raise for ordinary "could not
        determine" cases — report those via
        `VerificationResult.status`/`error_message` instead, so the
        coordinator's per-provider metrics stay accurate. An actual raised
        exception is still handled safely (the coordinator treats it as an
        ERROR result and keeps going), but it should be reserved for
        genuinely unexpected programming errors, not expected real-world
        outcomes like "mailbox does not exist."
        """


class EmailVerificationPort(VerificationProviderPort):
    """Base for providers that verify email addresses (e.g. a future
    NeverBounce, ZeroBounce, Kickbox, or Bouncer adapter).

    Fixes `supported_contact_types` to `{ContactType.EMAIL}` so a concrete
    subclass only has to implement `provider_id`, `display_name`, and
    `verify()`.
    """

    @property
    def supported_contact_types(self) -> frozenset[ContactType]:
        return frozenset({ContactType.EMAIL})


class PhoneVerificationPort(VerificationProviderPort):
    """Base for providers that verify phone numbers (e.g. a future Twilio
    Lookup, Numverify, or Abstract API adapter).

    Fixes `supported_contact_types` to `{ContactType.PHONE}` so a concrete
    subclass only has to implement `provider_id`, `display_name`, and
    `verify()`.
    """

    @property
    def supported_contact_types(self) -> frozenset[ContactType]:
        return frozenset({ContactType.PHONE})
