# Identity Resolution Engine

Implements Version 1 of the approved Identity Resolution RFC: determining
whether two or more observations refer to the same real-world Person or
Company. That RFC is the source of truth for *why* each design decision was
made; this README explains *how the code is put together*.

## Scope: what Version 1 does and does not do

**Does:** extract identity signals from already-cleaned records, classify
them into Strong/Moderate/Weak tiers, generate candidate matches, compute
explainable confidence scores, make auto-merge / candidate-review / new-
identity decisions, produce an audit trail entry for every decision, and
recompute confidence when new evidence arrives.

**Does not (Version 2 scope):** identity lineage redirects, merge rollback
windows, full reviewer workflows (confirm/reject/defer/escalate actions),
advanced merge history, or multi-stage lineage graphs. A recomputed
decision here produces an audit entry describing the transition; it does
not yet perform an actual merge/persistence action, wire into
`AuditLogRepository`, or touch any database — no concrete repositories or
ORM models exist yet (a separate, not-yet-reached task).

## How the pieces communicate

```
ResolveIdentityUseCase                  (application/use_cases/resolve_identity.py)
        |
        v
IdentityResolutionEngine                (engine.py)
        |
        |-- reads --> IdentityResolutionProfile  (config.py)      "tiers, weights, thresholds"
        |
        |-- 1. extract_identity()        (signal_extraction.py)   record -> ExtractedIdentity
        |-- 2. generate_candidates()      (candidate_generation.py) -> tuple[IdentityRecord, ...]
        |         (via IdentityCandidatePort, application/ports/)
        |-- 3. score_candidate()          (scoring.py)             -> ConfidenceScore, per candidate
        |-- 4. decide()                   (decision.py)            -> ResolutionDecision
        |
        v
IdentityResolutionResult                (application/dto/identity_resolution_models.py)
  = outcomes: tuple[IdentityResolutionOutcome, ...]
  + review_queue: tuple[ReviewQueueItem, ...]
  + audit_trail: tuple[IdentityAuditEntry, ...]
  + report: IdentityResolutionReport
  + metrics: IdentityResolutionMetrics
```

**Execution, per record (`IdentityResolutionEngine.resolve_record`):**
1. **Extract** every available identity signal for the requested Subject
   type (Person or Company) from the record's already-`cleaned_values` —
   never from raw, uncleaned data (RFC §9: signal comparison only works on
   normalized values).
2. **Generate candidates**: look up existing `IdentityRecord`s sharing at
   least one *blocking-eligible* signal, via the injected
   `IdentityCandidatePort`. A signal type marked
   `usable_for_candidate_generation=False` in the profile (title, by
   default) can never single-handedly surface a candidate.
3. **Score** every candidate independently and deterministically (see
   "Scoring algorithm" below).
4. **Decide**: any Auto-merge-band candidate wins (ties broken by score,
   then `identity_id`); otherwise every Candidate-review-band candidate is
   queued for review; otherwise the record becomes a new identity.
5. Every path produces exactly one `IdentityAuditEntry` — there is no
   silent decision.

## Scoring algorithm (`scoring.py`)

`score_candidate(extracted, candidate, profile)` is a **pure function** of
its three arguments — no randomness, no I/O, no hidden state. That is what
makes both determinism (this task's explicit requirement) and confidence
*recomputation* (RFC §10) fall out for free: recomputing a score is just
calling this function again with updated evidence, not a second algorithm.

1. For every incoming signal with a same-type signal on the candidate: an
   equal value is *supporting*; a different value is *contradicting* only
   if that signal type is `contradiction_sensitive` in the profile.
2. RFC §2's rule — "a single weak signal is never sufficient" — is
   enforced structurally: with no Strong-tier support, at least
   `profile.min_independent_signals_without_strong_match` distinct signal
   *types* must independently support the candidate, or the score is
   forced to `0.0` / `NO_MATCH` regardless of what the raw weighted sum
   would otherwise be.
3. Otherwise: `value = clamp(sum(supporting weights) - sum(contradiction
   penalties), 0.0, 1.0)`, banded against `auto_merge_threshold` /
   `candidate_review_threshold`.

Every supporting and contradicting signal considered is retained in the
returned `MatchExplanation` — a score is never a bare number (RFC §3, §8:
"every confidence decision must be explainable").

## Configuration (`config.py`)

Every scoring rule is configurable, per this task's explicit requirement —
nothing is a hardcoded literal in `scoring.py` or `candidate_generation.py`:

- `signal_definitions: dict[signal_type, SignalTypeDefinition]` — each
  entry's `tier`, `weight`, `usable_for_candidate_generation`, and
  `contradiction_sensitive` flags.
- `auto_merge_threshold` / `candidate_review_threshold` — the two band
  boundaries.
- `contradiction_penalty` — score subtracted per contradicting signal.
- `min_independent_signals_without_strong_match` — the weak-signal
  corroboration floor.
- `max_candidates_considered` — deterministic cap on candidate generation.

`IdentityResolutionProfile.validate()` fails the whole run before any
record is processed if the profile is self-contradictory (mirrors
`CleaningProfile.validate()`).

## Why `IdentityCandidatePort`, not `DigitalTwinRepository`

`domain/repositories/digital_twin_repository.py` is reserved for the real,
future Digital Twin entity and is generic over a `TypeVar` placeholder for
it — `domain/entities/` doesn't exist yet (a deliberate, separate future
task). `IdentityCandidatePort` (`application/ports/`) is scoped narrowly to
exactly what identity matching needs today: an id plus its known signals
(`IdentityRecord`). A future infrastructure adapter will implement this
port backed by the real `DigitalTwinRepository`/`CompanyRepository` once
domain entities exist. No concrete implementation exists yet; tests use an
in-memory fake (`tests/unit/identity_resolution/fixtures.py`).

## Adding a new signal type without modifying existing code

1. Add one entry to `DEFAULT_SIGNAL_DEFINITIONS` in `config.py` (tier,
   weight, and the two boolean flags).
2. Write one `_add_..._signal` helper in `signal_extraction.py` and call it
   from the appropriate `_extract_person_signals`/`_extract_company_signals`.

`scoring.py`, `candidate_generation.py`, and `decision.py` never change —
none of them name a specific signal type.

## Files

| File | Responsibility |
|---|---|
| `config.py` | `IdentityResolutionProfile`, `SignalTypeDefinition`, `default_profile`. |
| `signal_extraction.py` | `extract_identity` — record -> `ExtractedIdentity`. |
| `candidate_generation.py` | `generate_candidates` — blocking-eligible signal lookup, dedup, deterministic cap. |
| `scoring.py` | `score_candidate`, `recompute_confidence`. |
| `decision.py` | `decide`, `select_merge_target`, `review_candidates`. |
| `engine.py` | `IdentityResolutionEngine` — per-record and per-dataset orchestration. |
| `recomputation.py` | `recompute_review_item` — RFC §10, new-evidence-driven rescoring. |
| `application/ports/identity_candidate_port.py` | `IdentityCandidatePort`. |
| `application/dto/identity_resolution_models.py` | Every DTO: `IdentitySignal`, `ExtractedIdentity`, `IdentityRecord`, `ConfidenceScore`, `MatchCandidate`, `IdentityAuditEntry`, `ReviewQueueItem`, `IdentityResolutionResult`, etc. |
| `application/use_cases/resolve_identity.py` | `ResolveIdentityUseCase` — thin orchestration entry point. |
| `domain/exceptions/identity_resolution_exceptions.py` | `LeadIdentityResolutionError`, `InvalidIdentityResolutionConfigurationError`. |

Tests: `tests/unit/identity_resolution/` — signal extraction (including
missing-field and fallback-field behavior), candidate generation
(deduplication, capping, determinism, title's blocking exclusion), scoring
(every confidence band, contradiction handling, determinism, the weak-
signal corroboration rule), decision aggregation, an in-memory-port
end-to-end engine test for all three decision paths, and confidence
recomputation (band transitions from new evidence).
