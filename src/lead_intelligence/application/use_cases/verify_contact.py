"""The Contact Verification Framework's application-level orchestration
entry point.

WHY THIS FILE EXISTS, AND WHY IT'S SO THIN:
Mirrors EnrichSubjectUseCase's role exactly: this class knows nothing about
providers, priority, or profiles — it only knows how to hand one contact
detail to a VerificationCoordinator and return the VerificationReport. Real
orchestration logic lives in VerificationCoordinator; this is the stable
seam a future API/CLI layer calls.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationReport,
)
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)


class VerifyContactUseCase:
    """Verifies one contact detail using a pre-configured coordinator."""

    def __init__(self, coordinator: VerificationCoordinator) -> None:
        """Bind this use case to one already-configured coordinator.

        Args:
            coordinator: A VerificationCoordinator already constructed with
                its providers and VerificationProfile.
        """

        self._coordinator = coordinator

    def execute(
        self, contact_type: ContactType, subject_id: str, value: str
    ) -> VerificationReport:
        """Verify `value` and return the full VerificationReport.

        Args:
            contact_type: EMAIL or PHONE.
            subject_id: The Digital Twin id (or provisional identity id)
                this contact detail belongs to.
            value: The contact detail to verify (e.g. "ada@example.com").

        Returns:
            A VerificationReport containing every executed provider's
            result, the skipped-provider list, and run metrics.
        """

        logger.info(
            "Verify contact use case starting (subject_id={}, contact_type={})",
            subject_id,
            contact_type.value,
        )
        report = self._coordinator.verify(contact_type, subject_id, value)
        logger.info(
            "Verify contact use case finished: {} provider(s) executed, " "{} skipped",
            report.metrics.providers_executed,
            report.metrics.providers_skipped,
        )
        return report
