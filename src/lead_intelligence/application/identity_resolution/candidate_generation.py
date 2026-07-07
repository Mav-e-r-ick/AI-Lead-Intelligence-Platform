"""Finds existing IdentityRecords that could plausibly match one
ExtractedIdentity — the "blocking" step (RFC §12) that keeps the engine
from having to score every incoming record against every known identity.
"""

from __future__ import annotations

from loguru import logger

from lead_intelligence.application.dto.identity_resolution_models import (
    ExtractedIdentity,
    IdentityRecord,
)
from lead_intelligence.application.identity_resolution.config import (
    IdentityResolutionProfile,
)
from lead_intelligence.application.ports.identity_candidate_port import (
    IdentityCandidatePort,
)


def generate_candidates(
    extracted: ExtractedIdentity,
    port: IdentityCandidatePort,
    profile: IdentityResolutionProfile,
) -> tuple[IdentityRecord, ...]:
    """Look up every existing IdentityRecord sharing at least one
    blocking-eligible signal with `extracted`.

    Only signal types with `usable_for_candidate_generation=True` in the
    profile are queried — this is what keeps a Weak, corroboration-only
    signal like "title" from ever single-handedly surfacing a candidate
    (RFC §2). Results are deduplicated by `identity_id`, sorted
    deterministically (never left in port/dict iteration order, which is
    not guaranteed reproducible across runs), and capped at
    `profile.max_candidates_considered`.
    """

    seen: dict[str, IdentityRecord] = {}
    for signal in extracted.signals:
        definition = profile.definition_for(signal.signal_type)
        if not definition.usable_for_candidate_generation:
            continue
        for candidate in port.find_by_signal(signal.signal_type, signal.value):
            seen.setdefault(candidate.identity_id, candidate)

    ordered = sorted(seen.values(), key=lambda record: record.identity_id)
    capped = tuple(ordered[: profile.max_candidates_considered])

    logger.debug(
        "Candidate generation for {}: {} candidate(s) found ({} after cap of {})",
        extracted.record_reference,
        len(seen),
        len(capped),
        profile.max_candidates_considered,
    )
    return capped
