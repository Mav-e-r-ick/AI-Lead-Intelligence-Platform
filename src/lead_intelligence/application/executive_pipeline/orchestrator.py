"""ExecutiveProcessingOrchestrator: the Executive Processing Pipeline's
single orchestration point.

Given one existing (cleaned) executive record, runs it through every
module already built for this platform, in order:

1. Identity Resolution (only if an IdentityResolutionEngine was
   configured) — deciding which known identity this record refers to.
2. Enrichment (Company Website Provider — and Google Search Provider,
   where registered — via the existing EnrichmentCoordinator).
3. Search (only if a SearchCoordinator was configured) — Browser Search
   Provider et al., returning SearchResults (URLs only).
4. Search Extraction (only if a SearchExtractionEngine was configured) —
   turning those SearchResults' destination pages into
   ObservationCandidates.
5. Combining the ObservationCandidates from enrichment and search
   extraction into one evidence pool.
6. The Executive Comparison Engine (existing record vs. new observations).
7. The Inflection Detection Engine (comparison result -> business events).
8. The Verification Coordinator (email only, and only if one was
   configured) — verifying the executive's already-known email address,
   not a newly observed one.

`process()` handles one executive; `process_batch()` handles many —
continuing past any one executive's unexpected failure — and returns one
ExecutiveIntelligenceReport (every per-executive report plus batch
statistics: counts by status, error totals, execution time).

WHY THIS CLASS WIRES TOGETHER ALREADY-BUILT COORDINATORS/ENGINES INSTEAD OF
REIMPLEMENTING ANY OF THEM:
This task's explicit scope is "no new provider, no framework redesign."
Every module this orchestrator calls (IdentityResolutionEngine,
EnrichmentCoordinator, SearchCoordinator, SearchExtractionEngine,
ComparisonEngine, InflectionDetectionEngine, VerificationCoordinator) is
unmodified — this class only sequences calls to them and aggregates their
own result types into one ExecutiveProcessingReport.

WHY IDENTITY RESOLUTION'S OUTCOME IS RECORDED BUT ITS RESOLVED IDENTITY
ID IS NOT (YET) USED AS THE PIPELINE'S subject_id:
No persistence exists — there is no identity store to merge into, no
IdentityCandidatePort infrastructure adapter, and no durable id to carry
forward between runs. Swapping the caller's subject_id mid-pipeline for
an identity id that evaporates when the process exits would be motion
without progress. Version 1 records the engine's full
IdentityResolutionOutcome on the report (so the decision is visible and
auditable) and keeps the caller-supplied subject_id for every stage —
the honest wiring until persistence exists.

WHY SEARCH AND SEARCH EXTRACTION ARE SEPARATE OPTIONAL COLLABORATORS:
They are separate modules with separate jobs, per the approved Search
Layer RFC — search finds URLs, extraction reads them. A configuration
that searches but cannot extract collects evidence it can't use, so the
orchestrator logs a warning in that case (and still records which search
providers executed) rather than failing or silently pretending nothing
happened.

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

import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

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
    ExecutiveBatchStatistics,
    ExecutiveIntelligenceReport,
    ExecutiveProcessingReport,
    ExecutiveProcessingStatus,
)
from lead_intelligence.application.dto.identity_resolution_models import (
    IdentityResolutionOutcome,
)
from lead_intelligence.application.dto.inflection_models import InflectionReport
from lead_intelligence.application.dto.verification_models import (
    ContactType,
    VerificationReport,
)
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.ports.search_extraction_port import (
    SearchExtractionPort,
)
from lead_intelligence.application.search.coordinator import SearchCoordinator
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
        identity_resolution_engine: IdentityResolutionEngine | None = None,
        search_coordinator: SearchCoordinator | None = None,
        search_extraction_engine: SearchExtractionPort | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        """Configure an orchestrator bound to already-configured collaborators.

        Args:
            enrichment_coordinator: An EnrichmentCoordinator already
                constructed with the Company Website (and any other
                enrichment) providers registered (whichever are
                applicable/enabled is the coordinator's own decision —
                this orchestrator does not choose providers itself).
            comparison_engine: A ComparisonEngine already constructed with
                its ComparisonProfile.
            inflection_engine: An InflectionDetectionEngine already
                constructed with its InflectionRuleRegistry and
                InflectionProfile.
            verification_coordinator: A VerificationCoordinator already
                constructed with its email verification provider(s), or
                None to skip the verification stage entirely (the
                "Verification Coordinator ... if configured" scope).
            identity_resolution_engine: An IdentityResolutionEngine
                already constructed with its candidate port and profile,
                or None to skip the identity resolution stage entirely
                (no concrete IdentityCandidatePort infrastructure adapter
                exists yet — see module docstring).
            search_coordinator: A SearchCoordinator already constructed
                with its search provider(s) (e.g. BrowserSearchProvider)
                registered, or None to skip the search stage entirely.
            search_extraction_engine: Anything satisfying
                SearchExtractionPort (in production, the real
                SearchExtractionEngine from
                infrastructure/search/extraction/), or None to skip the
                search extraction stage entirely.
            clock: Returns the current UTC time. Override with a fixed
                value in tests for reproducible timestamps.
        """

        self._enrichment_coordinator = enrichment_coordinator
        self._comparison_engine = comparison_engine
        self._inflection_engine = inflection_engine
        self._verification_coordinator = verification_coordinator
        self._identity_resolution_engine = identity_resolution_engine
        self._search_coordinator = search_coordinator
        self._search_extraction_engine = search_extraction_engine
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

        identity_outcome = self._run_identity_resolution(
            existing_record, subject_id, stage_errors
        )
        providers_executed, observations = self._run_enrichment(
            subject_id, cleaned_values, stage_errors
        )
        search_providers_executed, search_observations = self._run_search_stages(
            subject_id, cleaned_values, stage_errors
        )
        providers_executed = providers_executed + search_providers_executed
        observations = observations + search_observations

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
            identity_resolution_outcome=identity_outcome,
        )

    def process_batch(
        self, records: Sequence[tuple[CleanedLeadRecord, str]]
    ) -> ExecutiveIntelligenceReport:
        """Process every (record, subject_id) pair and return one final
        ExecutiveIntelligenceReport.

        One executive's unexpected failure never stops the rest:
        `process()` already never raises for ordinary failures, and this
        method adds a batch-level guard on top (mirroring the Evaluation
        module's PipelineRunner), so even a genuinely unexpected exception
        for one record yields a FAILED report in its place and processing
        continues.

        Args:
            records: (existing_record, subject_id) pairs, in the order
                they should be processed — the same two arguments
                `process()` takes, per record.

        Returns:
            One ExecutiveIntelligenceReport: a report per input record,
            in input order, plus batch statistics.
        """

        started_at = self._clock()
        logger.info(
            "Executive batch processing starting: {} executive(s)", len(records)
        )
        start_perf = time.perf_counter()

        reports: list[ExecutiveProcessingReport] = []
        for existing_record, subject_id in records:
            try:
                reports.append(self.process(existing_record, subject_id))
            except Exception as exc:  # noqa: BLE001 - batch fail-safe: see docstring
                logger.error(
                    "Executive batch: unexpected error processing subject_id={}: {}",
                    subject_id,
                    exc,
                )
                at = self._clock()
                reports.append(
                    ExecutiveProcessingReport(
                        subject_id=subject_id,
                        executive_name=resolve_name(existing_record.cleaned_values),
                        providers_executed=(),
                        observations_collected=(),
                        comparison_result=None,
                        inflection_report=None,
                        verification_report=None,
                        status=ExecutiveProcessingStatus.FAILED,
                        stage_errors=(f"Unexpected error: {exc}",),
                        started_at=at,
                        completed_at=at,
                    )
                )

        execution_time_total_ms = (time.perf_counter() - start_perf) * 1000
        completed_at = self._clock()

        statistics = _compute_statistics(reports, execution_time_total_ms)
        logger.info(
            "Executive batch processing complete: {} executive(s) — "
            "{} succeeded, {} partial, {} failed, {} stage error(s), {:.1f}ms",
            statistics.total_executives,
            statistics.succeeded,
            statistics.partial,
            statistics.failed,
            statistics.stage_errors_total,
            statistics.execution_time_total_ms,
        )

        return ExecutiveIntelligenceReport(
            executive_reports=tuple(reports),
            statistics=statistics,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _run_identity_resolution(
        self,
        existing_record: CleanedLeadRecord,
        subject_id: str,
        stage_errors: list[str],
    ) -> IdentityResolutionOutcome | None:
        if self._identity_resolution_engine is None:
            return None
        try:
            outcome, _audit_entry, review_item = (
                self._identity_resolution_engine.resolve_record(
                    existing_record, SubjectType.PERSON, subject_id
                )
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            logger.warning(
                "Identity resolution stage raised for subject_id={}: {}",
                subject_id,
                exc,
            )
            stage_errors.append(f"Identity resolution failed: {exc}")
            return None

        # The audit entry and any review item have nowhere durable to go
        # yet (no persistence) — the review item is surfaced in the log so
        # a human can still see it; the full outcome rides on the report.
        if review_item is not None:
            logger.info(
                "Identity resolution queued subject_id={} for manual review "
                "(review item {})",
                subject_id,
                review_item.item_id,
            )
        return outcome

    def _run_search_stages(
        self,
        subject_id: str,
        cleaned_values: Mapping[str, Any],
        stage_errors: list[str],
    ) -> tuple[tuple[str, ...], tuple[ObservationCandidate, ...]]:
        """The Search + Search Extraction stages: find URLs, then read
        them. Each stage has its own error handling, so a search failure
        never blocks extraction of nothing (trivially) and an extraction
        failure never erases which search providers ran."""

        if self._search_coordinator is None:
            return (), ()

        known_attributes = _known_attributes(cleaned_values)
        try:
            search_result = self._search_coordinator.search(
                SubjectType.PERSON, subject_id, known_attributes
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            logger.warning("Search stage raised for subject_id={}: {}", subject_id, exc)
            stage_errors.append(f"Search failed: {exc}")
            return (), ()

        providers_executed = tuple(
            response.provider_id for response in search_result.provider_responses
        )

        if not search_result.results:
            return providers_executed, ()

        if self._search_extraction_engine is None:
            logger.warning(
                "Search found {} result(s) for subject_id={} but no "
                "SearchExtractionEngine is configured; results are recorded "
                "in the log only and produce no observations.",
                len(search_result.results),
                subject_id,
            )
            return providers_executed, ()

        try:
            extracted = self._search_extraction_engine.extract(
                subject_id, search_result.results
            )
        except Exception as exc:  # noqa: BLE001 - fail-safe: see module docstring
            logger.warning(
                "Search extraction stage raised for subject_id={}: {}",
                subject_id,
                exc,
            )
            stage_errors.append(f"Search extraction failed: {exc}")
            return providers_executed, ()

        return providers_executed, extracted

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


def _compute_statistics(
    reports: Sequence[ExecutiveProcessingReport], execution_time_total_ms: float
) -> ExecutiveBatchStatistics:
    by_status = {status: 0 for status in ExecutiveProcessingStatus}
    for report in reports:
        by_status[report.status] += 1
    return ExecutiveBatchStatistics(
        total_executives=len(reports),
        succeeded=by_status[ExecutiveProcessingStatus.SUCCESS],
        partial=by_status[ExecutiveProcessingStatus.PARTIAL],
        failed=by_status[ExecutiveProcessingStatus.FAILED],
        executives_with_errors=sum(1 for report in reports if report.stage_errors),
        stage_errors_total=sum(len(report.stage_errors) for report in reports),
        execution_time_total_ms=execution_time_total_ms,
    )
