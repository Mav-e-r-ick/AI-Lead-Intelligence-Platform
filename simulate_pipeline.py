#!/usr/bin/env python
"""Simulate the whole Executive Intelligence pipeline against a real
spreadsheet, on any machine, with no internet access and no API keys.

    python simulate_pipeline.py "your sheet.xlsx" --limit 20

WHAT THIS IS FOR:
`run_pipeline.py` is the real runner: it asks real search providers to go
find real evidence on the internet. That is the right tool once a machine
has unrestricted network access and (optionally) Google Custom Search
credentials. But it means that on a laptop behind a corporate proxy, on a
locked-down build agent, or before any API key exists, every stage after
"Search" receives nothing and there is nothing to look at — the pipeline
is working perfectly and appears to do nothing at all.

This script closes that gap. It runs the SAME production engines in the
SAME order that `run_pipeline.py` does, and fakes exactly one thing: the
evidence a search provider would have returned. That single substitution
is what makes every later stage observable:

    Database -> [SIMULATED evidence] -> Identity Resolution -> Comparison
      -> Inflection Detection -> Database Update -> Message Generation

WHAT IS REAL HERE, AND WHAT IS NOT:
  REAL   Import Engine, Cleaning Engine (your actual spreadsheet, all 68
         cleaning rules), IdentityResolutionEngine, ComparisonEngine,
         InflectionDetectionEngine + all 7 rules, ExecutiveRepository
         (a real SQLite database, really written to), the message
         generator, and ExecutiveProcessingOrchestrator itself.
  FAKE   Only the ObservationCandidates. No page is fetched, no browser
         is launched, no API is called, no network access is used.

Nothing here is a mock of a pipeline stage — the stages are the real,
shipped classes. Treat the inflections and messages it prints as "this is
what the platform WOULD do given that evidence", never as a finding about
a real executive.

HOW THE TWO PASSES WORK, AND WHY IT NEEDS TWO:
Detecting a *change* requires something to compare against, so a single
pass over a fresh database can only ever conclude "first time I've seen
this person". This script therefore does what a real deployment does over
time, in one run:

  Pass 1  Seed the database from the spreadsheet — "what we knew as of
          yesterday". No detection is attempted; this is the baseline.
  Pass 2  Run the real pipeline against simulated new evidence — "what
          today's search found". Identity Resolution matches each
          executive to their Pass 1 row, Comparison diffs the two, and
          everything downstream reacts to the difference.

DETERMINISM:
Which scenario an executive gets is derived from a stable hash of their
subject_id, so the same spreadsheet always produces the same simulation.
Re-running it is safe and comparable; there is no randomness to re-seed.
Use `--scenario NAME` to force every executive down one path instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# Windows consoles frequently default to a legacy code page that cannot
# encode the em-dashes/arrows this script prints, which would crash the
# run on output rather than on anything real. Force UTF-8 where possible.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

from loguru import logger

from lead_intelligence.application.cleaning import field_contract as fc
from lead_intelligence.application.cleaning.config import (
    default_profile as default_cleaning_profile,
)
from lead_intelligence.application.cleaning.pipeline import CleaningPipeline
from lead_intelligence.application.cleaning.rules import ALL_RULES as CLEANING_RULES
from lead_intelligence.application.comparison.config import (
    default_profile as default_comparison_profile,
)
from lead_intelligence.application.comparison.comparators import similarity
from lead_intelligence.application.comparison.engine import ComparisonEngine
from lead_intelligence.application.comparison.resolvers import (
    resolve_company,
    resolve_email,
    resolve_name,
    resolve_title,
)
from lead_intelligence.application.dto.cleaning_models import CleanedLeadRecord
from lead_intelligence.application.dto.comparison_models import ComparisonStatus
from lead_intelligence.application.dto.enrichment_models import (
    EnrichmentRequest,
    EnrichmentResponse,
    EnrichmentStatus,
    ObservationCandidate,
    SubjectType,
)
from lead_intelligence.application.dto.executive_pipeline_models import (
    ExecutiveProcessingReport,
)
from lead_intelligence.application.enrichment.config import EnrichmentProfile
from lead_intelligence.application.enrichment.coordinator import EnrichmentCoordinator
from lead_intelligence.application.enrichment.provider_registry import ProviderRegistry
from lead_intelligence.application.executive_pipeline.orchestrator import (
    ExecutiveProcessingOrchestrator,
)
from lead_intelligence.application.identity_resolution.config import (
    default_profile as default_identity_profile,
)
from lead_intelligence.application.identity_resolution.engine import (
    IdentityResolutionEngine,
)
from lead_intelligence.application.inflection.config import (
    default_profile as default_inflection_profile,
)
from lead_intelligence.application.inflection.engine import InflectionDetectionEngine
from lead_intelligence.application.inflection.registry import InflectionRuleRegistry
from lead_intelligence.application.inflection.rules import ALL_RULES as INFLECTION_RULES
from lead_intelligence.application.inflection.seniority import seniority_rank
from lead_intelligence.application.messaging.message_generator import (
    generate_message_for_report,
)
from lead_intelligence.application.ports.enrichment_provider_port import (
    EnrichmentProviderPort,
)
from lead_intelligence.application.use_cases.clean_dataset import CleanDatasetUseCase
from lead_intelligence.application.use_cases.import_dataset import ImportDatasetUseCase
from lead_intelligence.core.config import Settings
from lead_intelligence.infrastructure.database.base import Base
from lead_intelligence.infrastructure.database.executive_repository import (
    ExecutiveRepository,
)
from lead_intelligence.infrastructure.database.session import (
    create_engine_from_settings,
    create_session_factory,
)
from lead_intelligence.infrastructure.importers.excel.excel_reader import (
    ExcelSourceReader,
)

#: This script's own provider id, deliberately named so it is obvious in
#: every log line, every report, and every database row that the evidence
#: did not come from a real source.
SIMULATED_PROVIDER_ID = "simulated_evidence"

#: The scenarios one executive can be assigned. Each names a real
#: business situation the platform is meant to detect (or correctly
#: stay silent about).
SCENARIO_PROMOTION = "promotion"
SCENARIO_COMPANY_CHANGE = "company_change"
SCENARIO_CONTACT_CHANGE = "contact_change"
SCENARIO_CONFIRMED = "confirmed"
SCENARIO_NO_EVIDENCE = "no_evidence"

#: (scenario, weight) — how often each scenario is assigned when the
#: caller doesn't force one with `--scenario`. Deliberately weighted to
#: exercise every path in a small sample rather than to model a real
#: month's churn rate (in reality the overwhelming majority of executives
#: would be `confirmed` or `no_evidence`); this is a demonstration and
#: diagnostic tool, not a forecast.
DEFAULT_SCENARIO_MIX: tuple[tuple[str, int], ...] = (
    (SCENARIO_PROMOTION, 25),
    (SCENARIO_COMPANY_CHANGE, 20),
    (SCENARIO_CONTACT_CHANGE, 15),
    (SCENARIO_CONFIRMED, 20),
    (SCENARIO_NO_EVIDENCE, 20),
)

ALL_SCENARIOS: tuple[str, ...] = tuple(name for name, _ in DEFAULT_SCENARIO_MIX)

#: A ladder of concrete, unambiguously-ranked titles used to build a
#: *plausible* promotion: the simulated new title is the first rung whose
#: `seniority_rank` is strictly above the executive's current one. Using
#: the real ranking function (rather than a hardcoded "new title") is what
#: keeps the simulated evidence consistent with what PromotionRule will
#: actually conclude from it.
#: The final rung is deliberately the long "President and Chief Executive
#: Officer" form rather than a second bare C-title: for the single most
#: common title in real datasets of this kind, "Chief Experience Officer"
#: (rank 12), every shorter rung either fails on rank or is too similar to
#: register as a change ("Chief Executive Officer" scores 0.809 against a
#: 0.80 threshold). The long form still ranks 13 and scores 0.62, so a
#: promotion remains simulable for those executives instead of silently
#: producing no evidence at all.
PROMOTION_LADDER: tuple[str, ...] = (
    "Director",
    "Vice President",
    "Senior Vice President",
    "Executive Vice President",
    "President",
    "Chief Operating Officer",
    "Chief Executive Officer",
    "President and Chief Executive Officer",
)

#: Fictional acquirers used for the company-change scenario. Obviously
#: not-real names, so a simulated result can never be mistaken for a real
#: finding about a real company.
SIMULATED_ACQUIRERS: tuple[str, ...] = (
    "Northwind Holdings Inc.",
    "Contoso Group LLC",
    "Fabrikam Industries Inc.",
    "Litware Partners LLC",
    "Proseware Global Inc.",
)


def _stable_bucket(subject_id: str, modulo: int) -> int:
    """A stable, cross-platform bucket for `subject_id` in [0, modulo).

    WHY NOT `hash()`: Python's built-in `hash()` for strings is salted per
    process, so it would hand the same executive a different scenario on
    every run and make results impossible to compare. A hex digest is
    stable across runs, machines, and Python versions.
    """

    digest = hashlib.sha256(subject_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % modulo


def pick_scenario(subject_id: str, forced: str | None = None) -> str:
    """Which scenario `subject_id` gets — `forced` if given, otherwise a
    deterministic weighted pick from DEFAULT_SCENARIO_MIX."""

    if forced is not None:
        return forced

    total = sum(weight for _, weight in DEFAULT_SCENARIO_MIX)
    position = _stable_bucket(subject_id, total)
    cursor = 0
    for scenario, weight in DEFAULT_SCENARIO_MIX:
        cursor += weight
        if position < cursor:
            return scenario
    return DEFAULT_SCENARIO_MIX[-1][0]


def _title_fuzzy_threshold() -> float:
    """The live fuzzy threshold the ComparisonEngine will actually apply
    to `title`, read from the real default profile rather than hardcoded,
    so this script cannot drift out of step with it."""

    for rule in default_comparison_profile().field_rules:
        if rule.field_name == "title":
            return rule.fuzzy_threshold
    return 0.80


def promoted_title(current_title: str | None) -> str | None:
    """A title that is both genuinely more senior than `current_title` and
    textually distinct enough for the ComparisonEngine to see it as a
    change. None if no ladder rung satisfies both.

    WHY DISTINCTNESS IS CHECKED AND NOT ASSUMED:
    `title` is compared with a fuzzy strategy, so a higher-ranked title
    can still compare as MATCH if it merely *reads* like the old one.
    Real example from this dataset: "Chief Experience Officer" ->
    "Chief Executive Officer" is a genuine promotion by rank, but scores
    0.809 similarity against a 0.80 threshold, so Comparison calls it
    unchanged and nothing downstream fires. Simulated evidence that the
    Comparison Engine will discard is worse than useless — it makes a
    working pipeline look broken — so each rung is checked against the
    same `similarity` function and the same live threshold the engine
    itself uses, and the first rung that clears both bars is chosen.

    When `current_title` isn't recognizable to the ranking table at all,
    the top rung is returned if it is distinct: the change is still
    detected as CHANGED, but PromotionRule will (correctly, and visibly
    in this script's output) decline to call it a promotion, because it
    cannot establish a direction from a title it does not recognize.
    That case is counted separately in the summary.
    """

    if not current_title:
        return PROMOTION_LADDER[-1]

    threshold = _title_fuzzy_threshold()
    current_rank = seniority_rank(current_title)

    for candidate in PROMOTION_LADDER:
        if similarity(candidate, current_title) >= threshold:
            continue  # The engine would call this the same title.
        if current_rank is None:
            return candidate
        candidate_rank = seniority_rank(candidate)
        if candidate_rank is not None and candidate_rank > current_rank:
            return candidate
    return None


def build_observations(
    subject_id: str,
    cleaned_values: Mapping[str, Any],
    scenario: str,
    observed_at: datetime,
) -> tuple[ObservationCandidate, ...]:
    """The simulated evidence for one executive under one scenario.

    Every ObservationCandidate is stamped with SIMULATED_PROVIDER_ID and a
    clearly fictional `source_url`, so its origin stays obvious anywhere it
    later appears (logs, the report, the database).

    WHY A TITLE/COMPANY OBSERVATION ALWAYS SHIPS WITH A full_name ONE:
    Simulated evidence is only useful if it has the same *shape* real
    evidence would. SearchExtractionEngine fills `full_name`, `title`, and
    `company_name` from a single matched announcement pattern, so in
    production those three arrive together or not at all; `email` and
    `phone` are extracted independently, by their own regexes, and really
    can arrive alone (see fact_extraction.py). Emitting a bare `title`
    with no name would fabricate a shape the real engine never produces,
    and would make the pipeline look like it misfires on evidence it will
    never actually receive.
    """

    def observation(attribute: str, value: str) -> ObservationCandidate:
        return ObservationCandidate(
            subject_id=subject_id,
            attribute=attribute,
            value=value,
            provider_id=SIMULATED_PROVIDER_ID,
            observed_at=observed_at,
            source_url="https://simulated.invalid/not-a-real-source",
            evidence_type="simulated",
        )

    def announcement(attribute: str, value: str) -> tuple[ObservationCandidate, ...]:
        """An announcement-shaped fact set: the changed attribute plus the
        `full_name` that the same pattern match would always carry."""

        full_name = resolve_name(cleaned_values)
        name_observation = (
            (observation("full_name", full_name),) if full_name else ()
        )
        return (observation(attribute, value),) + name_observation

    if scenario == SCENARIO_NO_EVIDENCE:
        return ()

    if scenario == SCENARIO_PROMOTION:
        new_title = promoted_title(resolve_title(cleaned_values))
        if new_title is None:
            return ()
        return announcement("title", new_title)

    if scenario == SCENARIO_COMPANY_CHANGE:
        acquirer = SIMULATED_ACQUIRERS[
            _stable_bucket(subject_id, len(SIMULATED_ACQUIRERS))
        ]
        return announcement("company_name", acquirer)

    if scenario == SCENARIO_CONTACT_CHANGE:
        # Deliberately name-less: this is the one shape that really does
        # arrive on its own in production (a bio card's mailto: link with
        # no announcement prose around it).
        existing_email = resolve_email(cleaned_values) or "person@example.com"
        local, _, domain = existing_email.partition("@")
        return (observation("email", f"{local}.new@{domain or 'example.com'}"),)

    if scenario == SCENARIO_CONFIRMED:
        # Same title the record already holds: the search "found" the
        # executive and confirmed nothing changed. Proves MATCH works and
        # that no inflection fires off a confirmation.
        current_title = resolve_title(cleaned_values)
        if current_title is None:
            return ()
        return announcement("title", current_title)

    raise ValueError(f"Unknown scenario: {scenario!r}")


class SimulatedSearchProvider(EnrichmentProviderPort):
    """Returns pre-built simulated observations for each subject_id.

    Implements the real EnrichmentProviderPort so the real
    EnrichmentCoordinator drives it exactly as it drives a live provider —
    the coordinator, and everything downstream of it, cannot tell the
    difference and needs no special case. This class exists only in this
    script; nothing in `src/` knows about it.
    """

    def __init__(
        self, observations_by_subject: Mapping[str, tuple[ObservationCandidate, ...]]
    ) -> None:
        self._observations_by_subject = observations_by_subject

    @property
    def provider_id(self) -> str:
        return SIMULATED_PROVIDER_ID

    @property
    def display_name(self) -> str:
        return "Simulated Evidence (stands in for real internet search)"

    @property
    def supported_subject_types(self) -> frozenset[SubjectType]:
        return frozenset({SubjectType.PERSON})

    def fetch(self, request: EnrichmentRequest) -> EnrichmentResponse:
        observations = self._observations_by_subject.get(request.subject_id, ())
        return EnrichmentResponse(
            provider_id=self.provider_id,
            request_id=request.request_id,
            subject_id=request.subject_id,
            status=EnrichmentStatus.SUCCESS,
            observations=observations,
            error_message=None,
            started_at=request.requested_at,
            completed_at=request.requested_at,
        )


def build_repository(database_url: str) -> ExecutiveRepository:
    """The real ExecutiveRepository, over a real database. Defaults to a
    local SQLite file so the simulation's writes survive the process and
    can be inspected afterwards with any SQLite viewer."""

    engine = create_engine_from_settings(Settings(database_url=database_url))
    Base.metadata.create_all(engine)
    return ExecutiveRepository(create_session_factory(engine))


def build_orchestrator(
    repository: ExecutiveRepository,
    observations_by_subject: Mapping[str, tuple[ObservationCandidate, ...]],
) -> ExecutiveProcessingOrchestrator:
    """The real orchestrator, wired with the real Identity/Comparison/
    Inflection engines and one simulated evidence provider.

    `search_coordinator`/`search_extraction_engine`/`verification_coordinator`
    are left unset: this script's evidence arrives through the enrichment
    path, and no browser, network call, or API key is involved anywhere.
    """

    return ExecutiveProcessingOrchestrator(
        enrichment_coordinator=EnrichmentCoordinator(
            ProviderRegistry([SimulatedSearchProvider(observations_by_subject)]),
            EnrichmentProfile(name="simulation"),
        ),
        comparison_engine=ComparisonEngine(default_comparison_profile()),
        inflection_engine=InflectionDetectionEngine(
            InflectionRuleRegistry(INFLECTION_RULES), default_inflection_profile()
        ),
        identity_resolution_engine=IdentityResolutionEngine(
            repository, default_identity_profile()
        ),
    )


#: Where `discover_spreadsheet` looks, in order, when no path is given on
#: the command line. Keeps VS Code's plain "Run Python File" button
#: (which passes no arguments at all) working with no configuration.
SPREADSHEET_SEARCH_GLOBS: tuple[str, ...] = (
    "data/raw/*.xlsx",
    "data/*.xlsx",
    "*.xlsx",
)


def discover_spreadsheet(root: Path) -> Path | None:
    """The first .xlsx found under SPREADSHEET_SEARCH_GLOBS, or None.

    Excel lock-files (`~$foo.xlsx`, created while a workbook is open in
    Excel) are skipped: they are not real workbooks and opening one fails
    confusingly.
    """

    for pattern in SPREADSHEET_SEARCH_GLOBS:
        matches = sorted(
            path
            for path in root.glob(pattern)
            if path.is_file() and not path.name.startswith("~$")
        )
        if matches:
            return matches[0]
    return None


def load_records(
    excel_path: str, sheet: str | None, limit: int | None
) -> list[CleanedLeadRecord]:
    """Import and clean `excel_path` with the real Import and Cleaning
    Engines, returning at most `limit` cleaned records."""

    dataset = ImportDatasetUseCase(
        ExcelSourceReader(excel_path, sheet_name=sheet)
    ).execute(sheet)
    cleaning_result = CleanDatasetUseCase(
        CleaningPipeline(CLEANING_RULES, default_cleaning_profile())
    ).execute(dataset)
    records = list(cleaning_result.cleaned_dataset.cleaned_records)
    return records[:limit] if limit is not None else records


def current_field_value(
    report: ExecutiveProcessingReport, field_name: str, fallback: str | None
) -> str | None:
    """The newly observed value for `field_name` if Comparison found one,
    else `fallback` — so a message describes the executive's situation
    *after* the detected change, not the one it replaced. Mirrors
    `run_pipeline._current_field_value`; kept local so this script has no
    import-time dependency on the runner."""

    comparison_result = report.comparison_result
    if comparison_result is None:
        return fallback
    for comparison in comparison_result.field_comparisons:
        if comparison.field_name != field_name:
            continue
        if comparison.status in (ComparisonStatus.CHANGED, ComparisonStatus.NEW):
            return comparison.new_value or fallback
    return fallback


def changed_fields(report: ExecutiveProcessingReport) -> list[str]:
    """Human-readable "field: old -> new" strings for everything Comparison
    flagged as CHANGED or NEW."""

    if report.comparison_result is None:
        return []
    return [
        f"{c.field_name}: {c.existing_value!r} -> {c.new_value!r}"
        for c in report.comparison_result.field_comparisons
        if c.status in (ComparisonStatus.CHANGED, ComparisonStatus.NEW)
    ]


def print_executive(
    index: int,
    total: int,
    report: ExecutiveProcessingReport,
    scenario: str,
    fields_written: int,
    message: str | None,
) -> None:
    """One executive's full journey through every stage, as a readable
    block — the point of the whole script."""

    print(f"\n[{index}/{total}] {report.executive_name}  (scenario: {scenario})")
    print(f"    subject_id       : {report.subject_id}")

    identity = report.identity_resolution_outcome
    decision = identity.decision.value if identity else "not run"
    matched = (
        f" -> matched {identity.matched_identity_id}"
        if identity and identity.matched_identity_id
        else ""
    )
    print(f"    1 Identity       : {decision}{matched}")

    print(
        f"    2 Evidence       : {len(report.observations_collected)} "
        f"simulated observation(s)"
    )

    summary = report.comparison_result.summary if report.comparison_result else None
    if summary is None:
        print("    3 Comparison     : not run")
    else:
        detail = "; ".join(changed_fields(report)) or "nothing changed"
        print(
            f"    3 Comparison     : {summary.fields_changed} changed, "
            f"{summary.fields_matched} matched, {summary.fields_missing} missing"
            f"  ({detail})"
        )

    inflections = (
        report.inflection_report.inflections if report.inflection_report else ()
    )
    if inflections:
        for inflection in inflections:
            print(
                f"    4 Inflection     : {inflection.type.value} "
                f"(confidence {inflection.confidence:.2f}, rule {inflection.rule_id})"
            )
    else:
        print("    4 Inflection     : none detected")

    print(f"    5 Database       : {fields_written} field(s) written")
    print(f"    6 Message        : {message or '(none - nothing to reach out about)'}")

    if report.stage_errors:
        for error in report.stage_errors:
            print(f"    !  stage error   : {error}")


def build_result_row(
    report: ExecutiveProcessingReport,
    scenario: str,
    fields_written: int,
    message: str | None,
) -> dict[str, Any]:
    """One flat, spreadsheet-friendly row per executive."""

    identity = report.identity_resolution_outcome
    inflections = (
        report.inflection_report.inflections if report.inflection_report else ()
    )
    strongest = (
        max(inflections, key=lambda i: i.confidence) if inflections else None
    )
    summary = report.comparison_result.summary if report.comparison_result else None

    return {
        "Executive Name": report.executive_name or "",
        "Subject Id": report.subject_id,
        "Simulated Scenario": scenario,
        "Identity Decision": identity.decision.value if identity else "not_run",
        "Simulated Observations": len(report.observations_collected),
        "Fields Changed": summary.fields_changed if summary else 0,
        "What Changed": "; ".join(changed_fields(report)),
        "Inflection Detected": strongest.type.value if strongest else "none",
        "Inflection Confidence": (
            round(strongest.confidence, 2) if strongest else ""
        ),
        "Database Fields Written": fields_written,
        "Outreach Message": message or "",
        "Status": report.status.value,
        "Errors": "; ".join(report.stage_errors),
    }


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate counts across the simulated batch."""

    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))

    inflection_counts: dict[str, int] = {}
    for row in rows:
        detected = row["Inflection Detected"]
        if detected != "none":
            inflection_counts[detected] = inflection_counts.get(detected, 0) + 1

    return {
        "Executives Simulated": len(rows),
        "Succeeded": count(lambda r: r["Status"] == "success"),
        "Identity Recognized (not new)": count(
            lambda r: r["Identity Decision"] not in ("new_identity", "not_run")
        ),
        "Executives With A Detected Change": count(
            lambda r: r["Fields Changed"] > 0
        ),
        "Inflections By Type": inflection_counts,
        "Outreach Messages Generated": count(lambda r: r["Outreach Message"]),
        "Database Fields Written": sum(r["Database Fields Written"] for r in rows),
        # A title really did change, but no rule drew a conclusion from
        # it — almost always because `seniority_rank` doesn't recognize
        # the old title, so PromotionRule/DemotionRule can't establish a
        # direction. Worth surfacing: it is the honest limit of a keyword
        # ranking table, not a silent failure.
        "Title Changed But Direction Unknown": count(
            lambda r: "title:" in r["What Changed"]
            and r["Inflection Detected"] == "none"
        ),
        # The executive already sits at the top of PROMOTION_LADDER, so no
        # plausible promotion could be simulated for them at all. A
        # property of this script's ladder, never of the pipeline.
        "Promotion Not Simulable (already top rank)": count(
            lambda r: r["Simulated Scenario"] == SCENARIO_PROMOTION
            and r["Simulated Observations"] == 0
        ),
    }


def write_xlsx(rows: Sequence[Mapping[str, Any]], path: Path) -> None:
    import openpyxl

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Simulation"
    if rows:
        headers = list(rows[0].keys())
        sheet.append(headers)
        for row in rows:
            sheet.append([row[header] for header in headers])
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)


def write_json(
    summary: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    excel_path: str,
    path: Path,
) -> None:
    payload = {
        "simulation": True,
        "disclaimer": (
            "Evidence in this run was SIMULATED. No network request was made "
            "and no real source was consulted. Every inflection and message "
            "below shows what the platform would produce given that "
            "evidence - none of it is a finding about a real executive."
        ),
        "source_file": excel_path,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "executives": list(rows),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "excel_path",
        nargs="?",
        default=None,
        help=(
            "Path to your .xlsx file of executives. Optional: if omitted, "
            "the first spreadsheet found in data/raw/, data/, or the current "
            "directory is used, so VS Code's plain Run button works with no "
            "arguments."
        ),
    )
    parser.add_argument(
        "--sheet", default=None, help="Sheet name (default: auto-selected)."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="How many executives to simulate (default: 20).",
    )
    parser.add_argument(
        "--scenario",
        choices=ALL_SCENARIOS,
        default=None,
        help=(
            "Force every executive down one scenario instead of the "
            "deterministic mix. Useful for exercising a single path."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="simulation_output",
        help="Where to write results/report/database (default: simulation_output).",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "SQLAlchemy database URL. Defaults to a SQLite file inside "
            "--output-dir, so each run starts from a clean, inspectable database."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show the pipeline's own INFO logging (off by default: the "
        "per-executive report below is usually what you want).",
    )
    args = parser.parse_args(argv)

    logger.remove()
    if args.verbose:
        logger.add(sys.stderr, level="INFO")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    database_url = args.database_url or f"sqlite:///{output_dir / 'simulation.db'}"

    print("=" * 78)
    print("EXECUTIVE INTELLIGENCE PIPELINE - SIMULATION")
    print("=" * 78)
    print("Real: Import, Cleaning, Identity Resolution, Comparison, Inflection")
    print("      Detection, Database, Message Generation.")
    print("Simulated: ONLY the search evidence. No network, no API keys, no browser.")
    print("=" * 78)

    excel_path = args.excel_path
    if excel_path is None:
        discovered = discover_spreadsheet(Path.cwd())
        if discovered is None:
            print(
                "\nNo spreadsheet given and none found automatically.\n"
                "Looked for: " + ", ".join(SPREADSHEET_SEARCH_GLOBS) + "\n"
                "Put your .xlsx in data/raw/, or pass it explicitly:\n"
                '    python simulate_pipeline.py "path/to/your sheet.xlsx"'
            )
            return 1
        excel_path = str(discovered)
        print(f"\nNo spreadsheet given - using the one I found: {excel_path}")
        print("(pass a path explicitly if you meant a different file)")
    else:
        print(f"\nReading {excel_path} ...")

    if not Path(excel_path).is_file():
        print(f"\nThat file does not exist: {excel_path}")
        return 1

    records = load_records(excel_path, args.sheet, args.limit)
    if not records:
        print("No records found in that spreadsheet - nothing to simulate.")
        return 1
    batch = [
        (record, f"row:{record.raw_record.row_number}") for record in records
    ]
    print(f"Imported and cleaned {len(records)} executive(s).")

    repository = build_repository(database_url)

    # --- Pass 1: seed the baseline ------------------------------------
    # "What we already knew." Detecting a change needs a prior state to
    # compare against; without this pass every executive is simply new.
    print("\nPass 1: seeding the database with what the spreadsheet already knows ...")
    for record, subject_id in batch:
        repository.ensure_baseline(subject_id, record.cleaned_values)
    print(f"  {len(batch)} executive(s) recorded as the baseline.")

    # --- Pass 2: simulate today's search ------------------------------
    observed_at = datetime.now(timezone.utc)
    scenarios = {
        subject_id: pick_scenario(subject_id, args.scenario)
        for _, subject_id in batch
    }
    observations_by_subject = {
        subject_id: build_observations(
            subject_id, record.cleaned_values, scenarios[subject_id], observed_at
        )
        for record, subject_id in batch
    }

    print("\nPass 2: running the real pipeline against simulated new evidence ...")
    orchestrator = build_orchestrator(repository, observations_by_subject)
    intelligence_report = orchestrator.process_batch(batch)

    rows: list[dict[str, Any]] = []
    for index, (record, subject_id) in enumerate(batch, start=1):
        report = next(
            r
            for r in intelligence_report.executive_reports
            if r.subject_id == subject_id
        )
        fields_written = repository.apply_changes(
            subject_id, report.comparison_result, report.inflection_report
        )
        message = generate_message_for_report(
            report.inflection_report,
            report.executive_name or "",
            current_field_value(
                report, "company", resolve_company(record.cleaned_values)
            ),
            current_field_value(report, "title", resolve_title(record.cleaned_values)),
        )
        scenario = scenarios[subject_id]
        print_executive(
            index, len(batch), report, scenario, fields_written, message
        )
        rows.append(build_result_row(report, scenario, fields_written, message))

    summary = summarize(rows)

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for key, value in summary.items():
        if isinstance(value, dict):
            rendered = ", ".join(f"{k}={v}" for k, v in sorted(value.items())) or "none"
            print(f"  {key:34}: {rendered}")
        else:
            print(f"  {key:34}: {value}")

    results_path = output_dir / "simulation_results.xlsx"
    report_path = output_dir / "simulation_report.json"
    write_xlsx(rows, results_path)
    write_json(summary, rows, excel_path, report_path)

    print("\nWrote:")
    print(f"  {results_path}   (one row per executive)")
    print(f"  {report_path}   (machine-readable, same data)")
    print(f"  {output_dir / 'simulation.db'}   (the database that was actually written)")
    print(
        "\nReminder: the evidence was simulated. These inflections and messages "
        "show\nwhat the platform WOULD do with real search results - they are not "
        "findings\nabout real executives."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
