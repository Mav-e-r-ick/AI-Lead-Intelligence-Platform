# Inflection Detection Engine

Converts one `ComparisonResult` — the technical, field-by-field output of
the Executive Comparison Engine — into deterministic, explainable business
events: Promotion, Demotion, Company Change, Possible Resignation, Contact
Information Changed, Executive Newly Appeared, Executive No Longer Found.

## Scope: what Version 1 does and does not do

**Does:** run seven fixed detection rules against a `ComparisonResult`'s
`FieldComparison`s and produce one `InflectionReport` containing zero or
more `Inflection`s, each with a type, confidence, supporting comparisons,
a human-readable explanation, and a timestamp.

**Does not:** call an AI/LLM, perform a Google/web search, integrate with
LinkedIn, verify an email or phone number's deliverability, or send any
outreach message. This engine only interprets *evidence already present*
in a `ComparisonResult` — it never gathers new evidence itself.

## How the pieces communicate

```
DetectInflectionsUseCase                (application/use_cases/detect_inflections.py)
        |
        v
InflectionDetectionEngine               (engine.py)
        |
        |-- reads --> InflectionRuleRegistry  (registry.py)   "which rule objects exist"
        |-- reads --> InflectionProfile       (config.py)     "which rules are enabled, at what confidence"
        |-- calls --> InflectionRule.detect() (rules.py)      "does this rule's pattern match?"
        |
        v
InflectionReport                        (application/dto/inflection_models.py)
  = inflections: tuple[Inflection, ...]
```

**Per rule (`InflectionDetectionEngine.detect`), in registry order:**
1. Skip the rule if `InflectionProfile.is_enabled(rule)` is `False`.
2. Call `rule.detect(comparison_result)`. A rule returns an
   `InflectionDraft` (supporting comparisons + explanation, unstamped) if
   its pattern is present, else `None` — never raises for an ordinary
   "not present" outcome.
3. Stamp the draft into a full `Inflection`: `rule_id` and `detected_at`
   come from the engine, never from the rule itself (mirrors
   `QualityWarningDraft` → `QualityWarning` in the Cleaning Engine) —
   see `rule_base.py`'s module docstring.
4. Compute `confidence = clamp(profile.confidence_for(rule) *
   comparison_result.summary.confidence, 0.0, 1.0)` — a rule's own
   reliability, discounted by how trustworthy the underlying comparison
   run itself was.

## The seven Version 1 rules (`rules.py`)

| Rule | id | Fires when | Base confidence |
|---|---|---|---|
| `PromotionRule` | INF-001 | `title` is `CHANGED` and the new title's seniority rank is strictly higher. | 0.90 |
| `DemotionRule` | INF-002 | `title` is `CHANGED` and the new title's seniority rank is strictly lower. | 0.90 |
| `CompanyChangeRule` | INF-003 | `company` is `CHANGED`. | 0.95 |
| `PossibleResignationRule` | INF-004 | `title` is `MISSING` while `name` is not `MISSING`. | 0.50 |
| `ContactInfoChangedRule` | INF-005 | `email` and/or `phone` is `CHANGED`. | 0.70 |
| `ExecutiveNewlyAppearedRule` | INF-006 | `name` is `NEW`. | 0.85 |
| `ExecutiveNoLongerFoundRule` | INF-007 | `name` is `MISSING`. | 0.85 |

`ALL_RULES` is the registry-ready tuple of one instance per rule, in the
order above.

### Why Possible Resignation and Executive No Longer Found never both fire

Both react to "we can no longer confirm something about this executive,"
at different strengths. `ExecutiveNoLongerFoundRule` fires when the
**name itself** can't be confirmed (`MISSING`) — the strongest signal.
`PossibleResignationRule` fires only when the **title** can't be
confirmed while the **name** still resolves to something other than
`MISSING` — a softer, more tentative signal (hence "Possible").
`PossibleResignationRule` explicitly excludes the case where `name` is
also `MISSING`, so the two rules are mutually exclusive by construction,
not by a runtime priority/ordering rule.

## Title seniority ranking (`seniority.py`)

Promotion/Demotion direction is decided by `seniority_rank(title)`: a
small, explicit, versionable keyword table (`SENIORITY_KEYWORDS`), checked
as case-insensitive substrings of the title. Deliberately not AI — every
rank is traceable to the exact keyword that produced it. Not exhaustive;
an unrecognized title returns `None` (no promotion/demotion decision is
made), an honest Version 1 limitation, not a bug.

**Ranking takes the longest matching keyword, not the highest rank.**
Longer, more specific phrases ("vice president") often contain shorter,
less specific ones ("president") as substrings, even when the shorter
phrase's own rank is *higher* — a standalone "President" outranks a "Vice
President". Taking the highest rank among every matching keyword would
let "president" hijack the score for "Vice President". Taking the rank of
the longest matching keyword is order-independent and always prefers the
phrase that actually describes the title over a shorter substring it
happens to contain; ties in length are broken by the higher rank.

## Configuration (`config.py`)

- `InflectionRuleOverride` — per-rule `enabled` flag and optional
  `base_confidence` override.
- `InflectionProfile.rule_overrides` — a mapping keyed by `rule_id`; a
  rule with no entry runs enabled, at its own `InflectionRuleMetadata.base_confidence`.
- `InflectionProfile.validate()` fails the whole run before any rule runs
  if an override's `base_confidence` is outside `[0.0, 1.0]` — mirrors
  every other Profile in this platform.

## Files

| File | Responsibility |
|---|---|
| `rule_base.py` | `InflectionRuleMetadata`, `InflectionDraft`, `InflectionRule` (ABC), `get_field_comparison` helper. |
| `rules.py` | The seven concrete `InflectionRule` implementations + `ALL_RULES`. |
| `seniority.py` | `SENIORITY_KEYWORDS`, `seniority_rank` — deterministic title-seniority ranking. |
| `registry.py` | `InflectionRuleRegistry` — duplicate-`rule_id`-guarded lookup of rule objects. |
| `config.py` | `InflectionRuleOverride`, `InflectionProfile`, `default_profile`. |
| `engine.py` | `InflectionDetectionEngine` — runs enabled rules, stamps drafts, computes confidence, builds the report, logging. |
| `application/dto/inflection_models.py` | `InflectionType`, `Inflection`, `InflectionReport`. |
| `application/use_cases/detect_inflections.py` | `DetectInflectionsUseCase` — thin orchestration entry point. |
| `domain/exceptions/inflection_exceptions.py` | `LeadInflectionError`, `InvalidInflectionConfigurationError`, `DuplicateInflectionRuleError`. |

Tests: `tests/unit/inflection/` — seniority ranking edge cases, the
`get_field_comparison` helper, registry duplicate-id guarding, profile
validation and overrides, fire/no-fire coverage for all seven rules
(including the Possible-Resignation/Executive-No-Longer-Found mutual
exclusivity), and an end-to-end engine suite covering confidence
arithmetic, clamping, disabled rules, multiple simultaneous inflections,
determinism, and the use case wrapper.
