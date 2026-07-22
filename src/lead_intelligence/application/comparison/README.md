# Executive Comparison Engine

Compares one existing (cleaned) executive record against newly collected
`ObservationCandidate`s — e.g. from the Company Website Provider — and
identifies, field by field, what's the same, what's different, what's
missing, what's new, and what's ambiguous. Version 1 only identifies
differences; it never decides what a difference *means*.

## Scope: what Version 1 does and does not do

**Does:** compare five fields (name, title, company, email, phone)
between an existing record and newly collected observations, using
configurable exact or fuzzy strategies, and produce one `ComparisonResult`
containing a `FieldComparison` per field plus a `ComparisonSummary`.

**Does not:** call an AI/LLM, perform a Google/web search, integrate with
LinkedIn, verify an email or phone number's deliverability, or classify a
difference as a promotion, resignation, or any other kind of inflection
point. This engine answers "what changed," never "what does it mean" —
that interpretation is explicitly future work, layered on top of this
engine's output.

## How the pieces communicate

```
CompareExecutiveUseCase                 (application/use_cases/compare_executive.py)
        |
        v
ComparisonEngine                        (engine.py)
        |
        |-- reads --> ComparisonProfile       (config.py)      "which fields, which strategy, what threshold?"
        |-- reads --> EXISTING_VALUE_RESOLVERS (resolvers.py)   "how to read the existing side of each field"
        |-- uses  --> comparators.py                            "normalize_text / similarity / normalize_email / normalize_phone_digits"
        |
        v
ComparisonResult                        (application/dto/comparison_models.py)
  = field_comparisons: tuple[FieldComparison, ...]
  + summary: ComparisonSummary
```

**Per field (`ComparisonEngine._compare_field`):**
1. Resolve the existing value from `CleanedLeadRecord.cleaned_values` via
   that field's fixed resolver function (`resolvers.py`).
2. Collect every `ObservationCandidate` whose `attribute` is listed in the
   field's `observation_attributes`, deduplicated by normalized value
   (so "Ada Lovelace" and "ada   lovelace" from two different observations
   are treated as one candidate, not two).
3. Decide the verdict:

| Existing | New (after dedup) | Verdict |
|---|---|---|
| absent | none | `UNKNOWN` — nothing to compare. |
| any | 2+ distinct values | `CONFLICT` — the new observations disagree with each other; no single new value can be confidently reported. |
| present | none | `MISSING` — something we knew is absent from the new source. |
| absent | exactly one | `NEW` — newly discovered information. |
| present | exactly one | `MATCH` or `CHANGED`, per the field's configured strategy. |

For the last row: **EXACT** fields (email, phone) compare after a
field-specific normalizer (case-insensitive trim for email;
punctuation-stripped digits for phone); **FUZZY** fields (name, title,
company) compare via `comparators.similarity` (a `difflib.SequenceMatcher`
ratio in `[0.0, 1.0]`) against the field's configured `fuzzy_threshold`.

## Why `company`'s `observation_attributes` is `("company_name",)`

The Company Website Provider (`infrastructure/enrichment/company_website/`)
never reports a discovered company name — it fetches a company's site
*because* the company is already known. But `SearchExtractionEngine`
(the Federated Search redesign's fact-extraction stage) does emit a
`company_name` observation attribute when an announcement pattern names
one (see `infrastructure/search/extraction/fact_extraction.py`). Wiring
that attribute name here was a one-line profile change, exactly as
originally anticipated — no engine change — bringing `company` in line
with `name`/`title`, which are already wired the same way.

## Confidence (`ComparisonSummary.confidence`)

The fraction of fields that were comparable at all (excluding `UNKNOWN`,
which has nothing to be confident about) that produced a clear,
unambiguous verdict (`MATCH`/`CHANGED`/`MISSING`/`NEW`, not `CONFLICT`).
`CONFLICT` is the only thing that reduces confidence — it directly reflects
"the new data is ambiguous," which is exactly what should undermine trust
in the comparison. `0.0` if every field was `UNKNOWN` (nothing was ever
comparable, so there is nothing to be confident about).

## Configuration (`config.py`)

- `ComparisonFieldRule` — one per field: `observation_attributes`,
  `strategy` (`EXACT`/`FUZZY`), `fuzzy_threshold`.
- `ComparisonProfile.field_rules` — the ordered list of fields to compare;
  a narrower or reordered custom profile is a normal, supported use (see
  `test_config.py::test_custom_profile_can_narrow_the_field_set`).
- `ComparisonProfile.validate()` fails the whole run before any field is
  compared if the profile is self-contradictory (duplicate field names, a
  field with no matching resolver, an out-of-range fuzzy threshold) —
  mirrors every other Profile in this platform.

Existing-value *resolution* (how to read the existing side from
`field_contract.py`'s schema) is deliberately **not** part of this
configurable surface — see `resolvers.py`'s module docstring for why.

## Files

| File | Responsibility |
|---|---|
| `config.py` | `ComparisonFieldRule`, `ComparisonProfile`, `DEFAULT_FIELD_RULES`, `default_profile`. |
| `resolvers.py` | Existing-value extraction per field (`resolve_name`, `resolve_title`, `resolve_company`, `resolve_email`, `resolve_phone`) + `EXISTING_VALUE_RESOLVERS` registry. |
| `comparators.py` | `normalize_text`, `similarity`, `normalize_email`, `normalize_phone_digits`, `normalizer_for`. |
| `engine.py` | `ComparisonEngine` — per-field verdict determination, summary/confidence calculation, logging. |
| `application/dto/comparison_models.py` | `ComparisonStatus`, `ComparisonStrategy`, `FieldComparison`, `ComparisonSummary`, `ComparisonResult`. |
| `application/use_cases/compare_executive.py` | `CompareExecutiveUseCase` — thin orchestration entry point. |
| `domain/exceptions/comparison_exceptions.py` | `LeadComparisonError`, `InvalidComparisonConfigurationError`. |

Tests: `tests/unit/comparison/` — comparator primitives (normalization,
similarity, phone/email normalizers), existing-value resolver fallback
chains, profile validation, and an end-to-end engine suite covering all
six verdicts for both EXACT and FUZZY fields, conflict deduplication
(trivial formatting differences vs. genuinely distinct values),
summary/confidence arithmetic, determinism, and the use case wrapper.
