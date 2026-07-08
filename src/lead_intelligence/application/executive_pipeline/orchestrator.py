"""ExecutiveProcessingOrchestrator: the Executive Processing Pipeline's
single orchestration point.

Given one existing (cleaned) executive record, runs it through every
module already built for this platform, in order:

1. Enrichment (Company Website Provider + Google Search Provider, via the
   existing EnrichmentCoordinator).
2. Aggregating the ObservationCandidates every executed provider returned.
3. The Executive Comparison Engine (existing record vs. new observations).
4. The Inflection Detection Engine (comparison result -> business events).
5. The Verification Coordinator (email only, and only if one was
   configured) — verifying the executive's already-known email address,
   not a newly observed one.

WHY THIS CLASS WIRES TOGETHER ALREADY-BUILT COORDINATORS/ENGINES INSTEAD OF
REIMPLEMENTING ANY OF THEM:
This task's explicit scope is "no new provider, no framework redesign."
Every module this orchestrator calls (EnrichmentCoordinator, ComparisonEngine,
InflectionDetectionEngine, VerificationCoordinator) is unmodified — this
class only sequences calls to them and aggregates their own result types
into one ExecutiveProcessingReport.

WHY EACH STAGE IS WRAPPED IN ITS OWN try/except, RATHER THAN LETTING ANY
EXCEPTION PROPAGATE:
Mirrors the "one misbehaving component never sinks the whole run" pattern
already used by every coordinator in this platform (EnrichmentCoordinator
catches a raising provider; VerificationCoordinator catches a raising
provider). Taken to its logical conclusion at the top of the pipeline: an
unexpected exception in the Comparison Engine, say, must not prevent the
report from at least recording what enrichment already collected. This
orchestrator never raises for an ordinary processing failure — every
failure mode is reported via `ExecutiveProcessingReport.status`/
`stage_errors`, never a raised exception.

WHY VERIFICATION USES THE EXISTING RECORD'S EMAIL, NOT A NEWLY OBSERVED ONE:
The Contact Verification Framework's job is "confirm this contact detail
is safe to use before outreach" — that only makes sense for a value the
platform actually intends to use, which is the executive's existing,
already-known email (the same `resolve_email` the Executive Comparison
Engine itself uses), not an unverified value a provider merely observed
on some webpage.

WHY ENRICHMENT ISSUES ONE EnrichmentCoordinator.enrich() CALL PER SUBJECT
TYPE, NOT JUST ONE:
CompanyWebsiteProvider supports only `SubjectType.COMPANY` (it answers
"who does this company say its leaders are"); GoogleSearchProvider
supports only `SubjectType.PERSON` (it answers "what does the public web
say about this specific executive"). Both were deliberately scoped that
way in their own tasks, and changing either now would be exactly the kind
of "framework redesign" this task excludes. So this orchestrator calls
`enrich()` once per subject type the registered providers might support —
today that's PERSON and COMPANY — using the same opaque `subject_id` for
both (this pipeline has no separate Company Digital Twin id yet), and
merges whichever providers/observations each call produced. Each call is
wrapped in its own error handling, so one subject type's enrichment
failing never discards the other's results.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.comparison.resolvers import (
    resolve_email,
    resolve_name,
)
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.comparison_models import ComparisonResult
from lead_intelligence.application.dto.enrichment_models import (
    ObservationCandidate,
    SubjectType,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingReport,
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.inflection_models import InflectionReport
from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationReport,
)
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.verification.coordinator import (
    VerificationCoordinator,
)

#: known_attributes fields read from the existing record and passed
#: identically to every enrichment provider. Company Website reads
#: fc.URL/fc.COMPANY_NAME; Google Search reads fc.FIRST_NAME/fc.LAST_NAME/
#: fc.COMPANY_NAME/fc.TITLE — the same EnrichmentRequest is built once and
#: handed to both, per the Enrichment Provider Framework's own contract.
_KNOWN_ATTRIBUTE_FIELDS: tuple[str, ...] = (
    fc.FIRST_NAME,
    fc.LAST_NAME,
    fc.COMPANY_NAME,
    fc.TITLE,
    fc.URL,
)


class ExecutiveProcessingOrchestrator:
    """Processes one executive record through every existing pipeline
    stage and returns one combined ExecutiveProcessingReport."""

    def __init__(
        self,
        enrichment_coordinator: EnrichmentCoordinator,
        comparison_engine: ComparisonEngine,
        inflection_engine: InflectionDetectionEngine,
        verification_coordinator: VerificationCoordinator | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure an orchestrator bound to already-configured collaborators.

        Args:
            enrichment_coordinator: An EnrichmentCoordinator already
                constructed with the Company Website and Google Search
                providers registered (whichever are applicable/enabled is
                the coordinator's own decision — this orchestrator does
                not choose providers itself).
            comparison_engine: A ComparisonEngine already constructed with
                its ComparisonProfile.
            inflection_engine: An InflectionDetectionEngine already
                constructed with its InflectionRuleRegistry and
                InflectionProfile.
            verification_coordinator: A VerificationCoordinator already
                constructed with its email verification provider(s), or
                None to skip the verification stage entirely (the
                "Verification Coordinator ... if configured" scope).
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._enrichment_coordinator = enrichment_coordinator
        self._comparison_engine = comparison_engine
        self._inflection_engine = inflection_engine
        self._verification_coordinator = verification_coordinator
        self._clock = clock

    def process(
        self, existing_record: CleanedLeadRecord, subject_id: str
    ) -> ExecutiveProcessingReport:
        """Run `existing_record` through the full pipeline and return the
        combined report.

        Args:
            existing_record: The existing (cleaned) executive record to
                process — the same input the Executive Comparison Engine
                compares newly collected observations against.
            subject_id: An opaque id for this executive, passed identically
                to enrichment, comparison (as its `record_reference`), and
                verification, so every stage's own result traces back to
                this one run.

        Returns:
            One ExecutiveProcessingReport. Never raises for an ordinary
            processing failure — see module docstring.
        """

        started_at = self._clock()
        cleaned_values = existing_record.cleaned_values
        executive_name = resolve_name(cleaned_values)

        logger.info(
            "Executive processing pipeline starting: subject_id={}, executive='{}'",
            subject_id,
            executive_name,
        )

        if not executive_name:
            completed_at = self._clock()
            logger.warning(
                "Executive processing pipeline aborted: no executive name could "
                "be resolved (subject_id={})",
                subject_id,
            )
            return ExecutiveProcessingReport(
                subject_id=subject_id,
                executive_name=None,
                providers_executed=(),
                observations_collected=(),
                comparison_result=None,
                inflection_report=None,
                verification_report=None,
                status=ExecutiveProcessingStatus.FAILED,
                stage_errors=(
                    "No executive name could be resolved from the existing record.",
                ),
                started_at=started_at,
                completed_at=completed_at,
            )

        stage_errors: list[str] = []

        providers_executed, observations = self._run_enrichment(
            subject_id, cleaned_values, stage_errors
        )
        comparison_result = self._run_comparison(
            existing_record, observations, subject_id, stage_errors
        )
        inflection_report = self._run_inflection_detection(
            comparison_result, subject_id, stage_errors
        )
        verification_report = self._run_verification(
            cleaned_values, subject_id, stage_errors
        )

        completed_at = self._clock()
        status = _derive_status(comparison_result, stage_errors)

        logger.info(
            "Executive processing pipeline complete: subject_id={}, status={}, "
            "{} provider(s) executed, {} observation(s) collected, "
            "{} stage error(s)",
            subject_id,
            status.value,
            len(providers_executed),
            len(observations),
            len(stage_errors),
        )

        return ExecutiveProcessingReport(
            subject_id=subject_id,
            executive_name=executive_name,
            providers_executed=providers_executed,
            observations_collected=observations,
            comparison_result=comparison_result,
            inflection_report=inflection_report,
            verification_report=verification_report,
            status=status,
            stage_errors=tuple(stage_errors),
            started_at=started_at,
            completed_at=completed_at,
        )

    def _run_enrichment(
        self,
        subject_id: str,
        cleaned_values: Mapping[str, Any],
        stage_errors: list[str],
    ) -> tuple[tuple[str, ...], tuple[ObservationCandidate, ...]]:
        known_attributes = _known_attributes(cleaned_values)
        providers_executed: list[str] = []
        observations: list[ObservationCandidate] = []

        for subject_type in (SubjectType.PERSON, SubjectType.COMPANY):
            try:
                result = self._enrichment_coordinator.enrich(
                    subject_type, subject_id, known_attributes
                )
            except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
                logger.warning(
                    "Enrichment stage ({}) raised for subject_id={}: {}",
                    subject_type.value,
                    subject_id,
                    exc,
                )
                stage_errors.append(f"Enrichment ({subject_type.value}) failed: {exc}")
                continue

            providers_executed.extend(
                response.provider_id for response in result.provider_responses
            )
            observations.extend(result.observations)

        return tuple(providers_executed), tuple(observations)

    def _run_comparison(
        self,
        existing_record: CleanedLeadRecord,
        observations: tuple[ObservationCandidate, ...],
        subject_id: str,
        stage_errors: list[str],
    ) -> ComparisonResult | None:
        try:
            return self._comparison_engine.compare(
                existing_record, observations, subject_id
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            logger.warning(
                "Comparison stage raised for subject_id={}: {}", subject_id, exc
            )
            stage_errors.append(f"Comparison failed: {exc}")
            return None

    def _run_inflection_detection(
        self,
        comparison_result: ComparisonResult | None,
        subject_id: str,
        stage_errors: list[str],
    ) -> InflectionReport | None:
        if comparison_result is None:
            return None
        try:
            return self._inflection_engine.detect(comparison_result)
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            logger.warning(
                "Inflection detection stage raised for subject_id={}: {}",
                subject_id,
                exc,
            )
            stage_errors.append(f"Inflection detection failed: {exc}")
            return None

    def _run_verification(
        self,
        cleaned_values: Mapping[str, Any],
        subject_id: str,
        stage_errors: list[str],
    ) -> VerificationReport | None:
        if self._verification_coordinator is None:
            return None

        email = resolve_email(cleaned_values)
        if not email:
            logger.debug(
                "No known email for subject_id={}; skipping verification.",
                subject_id,
            )
            return None

        try:
            return self._verification_coordinator.verify(
                ContactType.EMAIL, subject_id, email
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            logger.warning(
                "Verification stage raised for subject_id={}: {}", subject_id, exc
            )
            stage_errors.append(f"Verification failed: {exc}")
            return None


def _known_attributes(cleaned_values: Mapping[str, Any]) -> dict[str, str]:
    known: dict[str, str] = {}
    for field_name in _KNOWN_ATTRIBUTE_FIELDS:
        value = cleaned_values.get(field_name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            known[field_name] = text
    return known


def _derive_status(
    comparison_result: ComparisonResult | None, stage_errors: list[str]
) -> ExecutiveProcessingStatus:
    if comparison_result is None:
        return ExecutiveProcessingStatus.FAILED
    if stage_errors:
        return ExecutiveProcessingStatus.PARTIAL
    return ExecutiveProcessingStatus.SUCCESS
