# Cleaning Engine

Implements every rule specified in
[`docs/CLEANING_RULES.md`](../../../../docs/CLEANING_RULES.md) (Rule IDs
`CLN-001`–`CLN-068`). That document is the source of truth for *what* each
rule does; this README explains *how the code is put together* so a new
rule can be added correctly.

## Scope: what this module does and does not do

**Does:** normalize field values (Safe stage, always; Business stage, only
if enabled), raise non-destructive Quality Warnings, and record a full
audit trail of every change and warning, with per-rule metrics.

**Does not:** verify anything against an external system, deduplicate
records, write to a database, or use AI/inference. Everything here is
deterministic and traceable to one specific rule ID and version.

## How the pieces communicate

```
CleanDatasetUseCase                     (application/use_cases/clean_dataset.py)
        |
        v
CleaningPipeline                        (pipeline.py)
        |
        |-- reads --> CleaningProfile    (config.py)          "what's enabled, with what parameters?"
        |-- runs  --> ALL_RULES          (rules/__init__.py)  "every CLN-### rule instance"
        |
        v
CleaningResult                          (application/dto/cleaning_models.py)
  = cleaned_dataset: CleanedLeadDataset
  + report: CleaningReport
  + metrics: CleaningMetrics
  + audit_trail: tuple[FieldChange | QualityWarning, ...]
```

**Execution, per record:**
1. Translate the `RawRecord`'s literal-keyed values into canonical-keyed
   values via `profile.field_mapping` (see `field_contract.py`).
2. **Safe stage** — every `NormalizationRule` with `stage=SAFE` runs, in
   registry order, unconditionally.
3. **Business stage** — only if `profile.enable_business_normalization`;
   within that, only rules where `profile.is_enabled(rule)` is `True`.
   Operates on the already-Safe-normalized values.
4. **Warning stage** — every `QualityCheckRule` where `profile.is_enabled(rule)`
   is `True`, always (independent of the Business master switch), against
   the final values. Structurally cannot modify data — see
   `application/ports/cleaning_rule_port.py`.
5. Every value change and warning is stamped with its rule's ID and
   version and appended to that record's audit trail.
6. A rule that raises is caught, logged, recorded as a `RuleExecutionFailure`
   (distinct from a data `QualityWarning`), and the record keeps processing
   — one bad rule/record never sinks the batch. A broken **profile**
   (`InvalidCleaningConfigurationError`) fails the entire run before any
   record is processed, via `rule.validate_config()` calls up front.

## Adding a new rule without modifying existing code (Open/Closed in practice)

`CleaningPipeline` never imports or names a specific rule — it only knows
`metadata.stage` and iterates whatever list it was constructed with. To add
rule `CLN-069`:

1. Check `rules/common.py` first — many rules are one-line instantiations
   of an existing generic (`WhitespaceNormalizationRule`,
   `MissingFieldWarningRuleSet`, `ThresholdWarningRule`, ...). If your new
   rule fits one of those shapes, just instantiate it in the right
   category module (`rules/identity.py`, `rules/contact.py`, etc.).
2. If it needs real logic, write one small class implementing
   `NormalizationRule` or `QualityCheckRule` in that category module.
3. Append the instance to that module's `*_RULES` tuple. `rules/__init__.py`'s
   `ALL_RULES` picks it up automatically.

`CleaningPipeline`, `CleaningProfile`, and every other existing rule are
untouched. This is the same dependency-injection seam used for
`SourceReaderPort` in the Import Engine, applied here to a list of rules
instead of a single adapter.

## Why generic rule base classes exist (`rules/common.py`)

Roughly half of the 68 rules share an underlying shape ("trim whitespace
for field group X," "warn if field Y is missing," "warn if two fields are
identical," ...). Each shape is implemented once in `common.py` and
*instantiated* per rule with that rule's own id/fields/parameters — keeping
the registry's total code volume manageable without weakening SOLID:
every instantiation still carries its own `RuleMetadata` and is
independently testable and independently toggleable. Sharing
implementation never means sharing identity.

## Two interfaces, not one — enforcing non-destructiveness by construction

`NormalizationRule.apply()` returns a mapping of changed fields.
`QualityCheckRule.apply()` returns a list of `QualityWarningDraft` —
**nothing else**. A warning rule is not merely asked to avoid mutating
data; its return type makes it impossible to do so. This is "make illegal
states unrepresentable" applied to CLEANING_RULES.md's promise that Warning
rules are non-destructive.

## Configuration (`config.py`)

- Safe rules have **no** configuration surface — if a rule needs a toggle,
  it isn't Safe by definition (see `docs/CLEANING_RULES.md` §2).
- Every Business/Warning rule is individually toggleable via
  `CleaningProfile.rule_overrides: dict[rule_id, RuleOverride]`
  (`enabled: bool | None`, `parameters: dict`).
- `enable_business_normalization: bool` is the stage-2 master switch.
- `field_mapping: dict[canonical_field, source_column_name]` keeps every
  rule source-agnostic — rules never see literal column headers like
  `"D-U-N-S® Number"`, only canonical names like `duns_number` (see
  `field_contract.py`). Defaults to the reference Excel schema
  (`DEFAULT_FIELD_MAPPING`), but any dataset can supply its own mapping.
- A rule with a required parameter (e.g. `CLN-016`'s `default_region`)
  overrides `validate_config(profile)` to fail fast, before any record is
  processed, if enabled without it.

## Reference data (`reference_data/`)

Small, curated, versioned static tables (acronyms, name particles, legal
suffixes, US states, country codes, classification codes) — starting
points grown from real evidence gathered during Import Engine dataset
profiling, not fabricated "complete" tables. Each is documented as
overridable via profile parameters, the same "swap the data, keep the
rule" principle used for external vendors elsewhere in this platform.

## Files

| File | Responsibility |
|---|---|
| `field_contract.py` | Canonical field-name vocabulary + the reference dataset's default mapping. |
| `config.py` | `CleaningProfile`, `RuleOverride`. |
| `pipeline.py` | `CleaningPipeline` — the 3-stage orchestrator. |
| `rules/common.py` | Generic, parameterized rule base classes. |
| `rules/{identity,contact,company,address,financial,industry,metadata,cross_field}.py` | Bespoke rule classes + each category's `*_RULES` tuple. |
| `rules/phone_formatting.py` | Shared E.164 helper for CLN-016 and CLN-067. |
| `rules/__init__.py` | `ALL_RULES` — every rule, in Rule ID order. |
| `reference_data/*.py` | Curated static lookup tables. |
| `application/ports/cleaning_rule_port.py` | `NormalizationRule`, `QualityCheckRule`, `RuleMetadata`, `RuleStage`, `RuleCategory`. |
| `application/dto/cleaning_models.py` | `FieldChange`, `QualityWarning`, `CleanedLeadRecord`, `CleaningMetrics`, `CleaningReport`, `CleaningResult`. |
| `application/use_cases/clean_dataset.py` | `CleanDatasetUseCase` — thin orchestration entry point. |
| `domain/exceptions/cleaning_exceptions.py` | `LeadCleaningError`, `InvalidCleaningConfigurationError`, `RuleExecutionError`. |

Tests: `tests/unit/cleaning/` — framework tests, generic-rule-class tests,
a registry-wide consistency sweep (every rule's metadata checked against
CLEANING_RULES.md's invariants), and targeted behavior tests for the
bespoke (non-generic) rules.

## Known limitation found during verification

`CLN-066` (Email Domain vs. Company Domain mismatch) initially fired on
~98% of the reference dataset's records — nearly every company URL is
stored as `http://www.example.com` while emails never carry a `www.`
subdomain, so the comparison was almost always a false mismatch. Fixed by
stripping a leading `www.` before comparing (see `rules/cross_field.py`);
verified this dropped the warning rate to ~17.5%, a plausible real signal.
