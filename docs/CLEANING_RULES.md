# Cleaning Rule Registry

| | |
|---|---|
| **Document status** | Draft specification — precedes implementation |
| **Document version** | 1.0.0 |
| **Owner** | AI Lead Intelligence Platform — Architecture |
| **Applies to** | The Cleaning Engine (`application/cleaning/`) |

This document is the **official, permanent specification** for every cleaning
rule in the platform. Once the Cleaning Engine is implemented, its code must
conform to this registry — not the other way around. If an implementer finds
a reason to deviate from a rule as specified here, the correct order of
operations is: update this document, get it reviewed, *then* change the code.

This document assumes the previously approved Cleaning Engine architecture:
a three-stage pipeline (**Safe/Lossless → Business → Warning**) executed by a
`CleaningPipeline` over records produced by the Import Engine, governed by a
`CleaningProfile`, implementing the `NormalizationRule` and `QualityCheckRule`
interfaces, and producing `CleanedLeadRecord` objects carrying a
`field_changes` audit trail and a `warnings` list. This document does not
re-derive that architecture — it catalogs the individual rules that plug into
it.

**No Python code appears in this document, and none of it has been
implemented yet.** Every rule below is written as an implementation-ready
specification: an engineer should be able to build, test, and code-review a
rule using nothing but its entry here.

---

## Table of Contents

1. [Purpose & Scope](#1-purpose--scope)
2. [How to Read a Rule Entry](#2-how-to-read-a-rule-entry)
3. [Rule Naming Convention](#3-rule-naming-convention)
4. [Rule Lifecycle](#4-rule-lifecycle)
5. [Versioning Strategy](#5-versioning-strategy)
6. [Logging Strategy](#6-logging-strategy)
7. [Audit Trail Strategy](#7-audit-trail-strategy)
8. [Metrics Collected Per Rule](#8-metrics-collected-per-rule)
9. [Rule Catalog](#9-rule-catalog)
   - [9.1 Identity](#91-identity)
   - [9.2 Contact](#92-contact)
   - [9.3 Company](#93-company)
   - [9.4 Address](#94-address)
   - [9.5 Financial](#95-financial)
   - [9.6 Industry](#96-industry)
   - [9.7 Metadata](#97-metadata)
   - [9.8 Cross-Field Rules](#98-cross-field-rules)
10. [Rule ID Index](#10-rule-id-index)

---

## 1. Purpose & Scope

This registry exists so that, years from now, an engineer who has never met
anyone on today's team can answer three questions without reading code:

1. **What does this rule do, exactly?** (Purpose, Description, Input/Output examples)
2. **Is it safe to change or disable?** (Type, Configurable, Default Enabled, Dependencies, Potential Risks)
3. **How do I know it's still working correctly?** (Test Cases, Metrics)

Every rule in the platform — whether it silently normalizes a value or
silently observes one — has a permanent entry here. A rule that exists in
code but not in this document is a defect, not a shortcut.

**Out of scope for this registry** (by design, per the approved Cleaning
Engine architecture): verification against external systems, deduplication
across records, database persistence, and AI/inference-based transformation.
None of the rules below call an external service or claim anything about the
real world — they only observe and normalize the string/value already in
hand.

---

## 2. How to Read a Rule Entry

Every rule uses the same template:

| Field | Meaning |
|---|---|
| **Rule ID** | Permanent, never reused, never renumbered. |
| **Rule Name** | Short, descriptive, verb-or-noun-phrase. |
| **Category** | One of the 8 sections in this document. |
| **Field(s)** | Which field(s) the rule reads and/or writes. |
| **Type** | `Safe (Lossless)`, `Business`, or `Warning` — see the three-category definitions carried over from the approved architecture, restated briefly below. |
| **Configurable** | Whether the rule (or its parameters) can be adjusted via a `CleaningProfile`. |
| **Default Enabled** | Whether a caller who supplies no explicit override gets this rule running. See the **Default-Enabled Policy** in §3. |
| **Dependencies** | Other rules (by ID) or pipeline stages that must run first, if any. |
| **Purpose** | One sentence: why this rule exists. |
| **Rule Description** | What it actually does, precisely enough to implement from. |
| **Input Example / Output Example** | A concrete before/after, drawn from real patterns observed during dataset profiling wherever possible. |
| **Potential Risks** | What could go wrong if this rule is enabled, misconfigured, or has a bug. |
| **Test Cases** | Acceptance criteria — these are meant to become the rule's actual test suite once implemented. |

**Three-category recap** (full rationale lives in the approved architecture
discussion, not repeated here):

- **Safe (Lossless):** can never turn a correct value into a wrong one, for
  any organization or dataset. Always runs. Never configurable.
- **Business:** improves consistency but encodes a judgment call with no
  single universally correct answer. Always individually toggleable.
- **Warning:** a non-destructive, purely syntactic observation ("does this
  look right?"), never a claim about external truth ("is this real?"). Never
  modifies data. Individually toggleable with configurable thresholds.

---

## 3. Rule Naming Convention

- **Rule ID format:** `CLN-###`, three-digit, zero-padded, assigned
  **sequentially across the entire registry** — not per category. A single
  global namespace means a rule's ID never has to change if it's later
  reclassified into a different category, and a log line or audit entry can
  reference `CLN-042` unambiguously without needing category context.
- **Rule IDs are permanent.** Once assigned, an ID is never reused — even
  after a rule is deprecated (§4), its ID stays retired forever. New rules
  always take the next unused number.
- **Rule Name format:** Title Case, descriptive of the *transformation or
  check performed*, not just the field it touches (e.g., "Title Acronym
  Casing Correction," not "Title Rule 2"). Names should be recognizable in a
  log line or code review comment without needing to open this document.
- **Field-group prefixes are not used in Rule IDs.** They were considered
  and rejected: a prefix like `IDN-004` would need to change if a rule moved
  category, breaking every historical audit-trail reference to it.

### Default-Enabled Policy

This is the governing heuristic for setting **Default Enabled** on any rule,
present or future — stated explicitly so it can be applied consistently
without re-litigating it every time:

> **A Business rule defaults to Enabled only if it fixes a specific,
> evidenced defect** (e.g., a casing bug observed in real data). **A
> Business rule defaults to Disabled if it encodes a stylistic or
> organizational preference with no single correct answer** (casing
> conventions, abbreviation formats, suffix stripping, unit assumptions).
> Safe rules are always Enabled. Warning rules are always Enabled unless a
> specific rule is judged too noisy for general use (documented per-rule if so).

---

## 4. Rule Lifecycle

Every rule moves through exactly three states:

**Draft** — The rule has a reserved Rule ID and a complete specification
entry in this document, but its implementation either doesn't exist yet or
hasn't passed review and testing. Draft rules must never run against
production data and must not be selectable in a `CleaningProfile`.
*As of this document's version (1.0.0), every rule below is in Draft state* —
this registry was written before any Cleaning Engine code exists, by design
(today's deliverable is the specification, not the implementation).

**Approved** — The rule is implemented, unit-tested against every Test Case
in its entry, and has passed code review. It is eligible for inclusion in a
`CleaningProfile`. A rule is promoted from Draft to Approved individually, as
its implementation lands — not in a single batch — so this document's status
per rule will diverge from its neighbors over time as implementation
proceeds.

**Deprecated** — The rule must no longer be applied to new data. Its entry
in this document is **never deleted** — it is marked `[DEPRECATED]` in its
heading, with a **Deprecation Reason** and, if applicable, a **Replaced By**
pointer to the successor Rule ID, appended to its entry. This preservation
is required because historical `CleanedLeadRecord` audit trails may
reference a deprecated rule's ID and version indefinitely; the spec they
point to must still be readable.

**Promotion/demotion requires:**
- Draft → Approved: implementation exists, all Test Cases pass as automated
  tests, code review sign-off recorded.
- Approved → Deprecated: architecture review sign-off, a documented
  Deprecation Reason, and (if a replacement exists) that replacement rule
  reaching Approved status first, so there is never a gap where neither rule
  is active.
- A rule never moves backward from Deprecated to Approved. A revived idea
  gets a new Rule ID and a fresh Draft entry, referencing the old one for
  context.

---

## 5. Versioning Strategy

Two independent things are versioned:

**1. This document**, as a whole, using semantic versioning
(`MAJOR.MINOR.PATCH`), tracked in a version history table maintained at the
top of this file going forward:
- **MAJOR** — a breaking change to a rule's documented behavior, or a
  category restructuring.
- **MINOR** — new rules added, or a rule's lifecycle state changes.
- **PATCH** — clarifications, corrected examples, typo fixes — no behavior change.

**2. Each individual rule's logic**, versioned independently
(e.g., "CLN-004 v1," then "CLN-004 v2" once its acronym dictionary is
expanded in a way that changes output for previously-unaffected input). A
rule's **version increments whenever its logic could produce a different
result for input it has already processed before** — expanding a lookup
table, changing a regex, adjusting a threshold all count; fixing a comment
or docstring does not.

**This is a hard requirement, not a suggestion:** every `FieldChange` and
`QualityWarning` recorded in a `CleanedLeadRecord`'s audit trail must store
**both** the Rule ID **and** the rule version that produced it — never the ID
alone. Without the version, "CLN-016 changed this phone number" is
unfalsifiable six months from now when CLN-016 is on v4 and its v1 behavior
is suspected of a bug; with the version, every historically affected record
can be found precisely.

**Behavior-changing version bumps go through Draft again** — a new rule
*version* (not a new Rule ID) that changes existing output must itself be
reviewed and explicitly rolled out via profile configuration, never silently
substituted under an existing "Approved" rule while a run is in flight.

---

## 6. Logging Strategy

The platform's existing `loguru`-based logging (see `core/logging.py`) is
the logging backend; this section specifies what the Cleaning Engine logs
and at what level.

| Level | What gets logged |
|---|---|
| **INFO** | Run-level milestones only: pipeline start, each stage's completion with aggregate counts ("Stage 1 (Lossless) complete: 2,644 records, 3,981 field changes"), pipeline completion with total warnings raised. |
| **DEBUG** | Per-rule, per-record execution: rule ID + version, record provenance (`row_number`, `sheet_name`, `source_path` — inherited from the `RawRecord`), field(s) touched, outcome (changed / unchanged / warning-raised). |
| **WARNING** | A rule **execution failure** — the rule itself threw an unexpected exception (an engineering fault, per the pipeline's fail-safe design). This is distinct from a data-quality `QualityWarning` and must be visually/structurally distinguishable in logs from one. |
| **ERROR** | Conditions that abort the entire run — chiefly `InvalidCleaningConfigurationError`. |

**Privacy requirement, non-negotiable given this platform processes real
people's data:** DEBUG-level logs may contain PII (an old/new email or phone
value). DEBUG-level logging must be an explicit opt-in flag, off by default
in any environment other than local development, and any long-lived log
sink (not an ephemeral local terminal) must redact or hash field values
rather than storing them in plaintext. INFO-level logs must never contain
field values — aggregate counts only.

---

## 7. Audit Trail Strategy

The audit trail is not a separate logging system — it is data, carried
**with** the `CleanedLeadRecord` itself (per the approved architecture),
because a log line can be lost, rotated, or misconfigured, but the record's
own audit trail travels with it wherever it's persisted.

**Guarantee this strategy exists to uphold:** given any `CleanedLeadRecord`,
it must always be possible to answer — without consulting anything outside
the record itself — *"what was the original value, which rule (ID and
version) changed it, in which stage, and when?"*

- Every value change produces exactly one `FieldChange` entry: rule ID +
  version, field name, old value, new value, stage, timestamp.
- Every warning produces exactly one `QualityWarning` entry: rule ID +
  version, field(s), warning code, message, timestamp.
- The audit trail is **append-only** — entries are never edited or removed,
  mirroring the immutability already designed into `RawRecord`/`FieldChange`
  as frozen structures. Correcting a mistaken past cleaning run means adding
  a new run's entries, never rewriting old ones.
- The original `RawRecord` is retained, unmodified, inside every
  `CleanedLeadRecord` — the audit trail is always diffable against the true
  source, not just against the previous cleaning stage's output.
- **Forward-looking requirement, for whoever builds persistence later:** the
  audit trail must be persisted alongside the cleaned record, not discarded
  after the run completes. This document can't enforce that (the Cleaning
  Engine itself never writes to a database, per its approved scope), but it
  records the requirement so it isn't lost.

---

## 8. Metrics Collected Per Rule

Collected once per rule, per `CleaningPipeline` run, and rolled into the
run's aggregate stats (attached to the resulting dataset, mirroring how
`SourceMetadata` reports on an Import Engine run):

| Metric | Definition |
|---|---|
| `records_evaluated` | Records the rule was applicable to (may be less than the full dataset if the rule's field isn't present in this dataset's field mapping). |
| `records_affected` | Records where the rule actually changed a value (Safe/Business) or raised a warning (Warning). |
| `records_skipped` | Records skipped because the rule was disabled in the active profile, or its field(s) were unmapped for this source. |
| `execution_time_total_ms` | Total time this rule spent executing across the run. |
| `execution_time_avg_ms_per_record` | Derived from the above; the metric to watch for a rule becoming a performance bottleneck (e.g., an inefficient regex). |
| `failure_count` | Records where the rule itself threw an unexpected exception (caught by the pipeline's fail-safe handling, per §6's WARNING-level logging). |
| `warning_count` | (Warning-type rules only) total warnings raised — may exceed `records_affected` if a single rule can raise more than one warning per record. |
| `last_run_timestamp` | When this rule last executed, across any dataset — useful for spotting rules that have quietly gone unused and are deprecation candidates. |

These are per-run numbers first; nothing here mandates a long-term
metrics store today. But collecting them in this consistent shape from the
first implementation is what makes a future trend question — *"is CLN-016's
failure rate climbing?"* — answerable later without a redesign.

---

## 9. Rule Catalog

Field names below are the literal source column headers from the reference
dataset profiled during the Import Engine task. Per the approved
architecture's field-mapping design, rules are actually implemented against
a **canonical field name** (e.g., `EMAIL`, not the literal string `"Email"`)
so they remain portable across differently-named future sources; the
literal names are used here only because they're concrete and traceable
back to real evidence.

---

### 9.1 Identity

*Fields: `First Name`, `Last Name`, `Title`, `Contact Level`, `Job Function`*

#### CLN-001 — Trim & Normalize Whitespace (Identity Fields)

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | First Name, Last Name, Title, Contact Level, Job Function |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None — runs first in the Lossless stage for this category |

**Purpose:** Guarantee every downstream rule in this category operates on
whitespace-clean, Unicode-normalized text without re-implementing that hygiene itself.

**Rule Description:** Trims leading/trailing whitespace; collapses internal
runs of whitespace to a single space; applies Unicode NFC normalization;
strips non-printable control characters.

**Input Example:** `"  Cristina  "` → **Output Example:** `"Cristina"`

**Potential Risks:** None identified — this is the textbook lossless case;
no legitimate name/title relies on leading, trailing, or doubled whitespace.

**Test Cases:**
- Given `" Ada "`, expect `"Ada"`.
- Given `"Chief Experience Officer"` (non-breaking spaces), expect `"Chief Experience Officer"`.
- Given `""` (empty string), expect `""` unchanged (no error).
- Given `None`, expect `None` unchanged (rule is a no-op on absent values).

---

#### CLN-002 — Name Casing Standardization

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | First Name, Last Name |
| **Type** | Business |
| **Configurable** | Yes — target casing style; particle exception list is user-supplied reference data |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-001 |

**Purpose:** Make display-facing names consistently capitalized, since
source data casing is inconsistent across export tools.

**Rule Description:** Applies Title Case, except for entries matching a
configurable exception list of name particles/patterns (`Mc`, `Mac`, `O'`,
`van`, `von`, `de`, `la`, etc.), which follow their own established
capitalization rule rather than naive per-word Title Case.

**Input Example:** `"o'brien"` → **Output Example:** `"O'Brien"`

**Potential Risks:** The exception list can never be fully complete for
every naming tradition worldwide; gaps produce incorrectly cased names.
Mitigation: treat the exception list as living reference data, expanded from
real production data, not a one-time static list.

**Test Cases:**
- Given `"john"`, expect `"John"`.
- Given `"mcdonald"`, expect `"McDonald"`.
- Given `"jean-pierre"`, expect `"Jean-Pierre"` (hyphen-aware).
- Given `"VAN DER BERG"`, expect `"van der Berg"` (particle-aware, not naive Title Case).

---

#### CLN-003 — Name Suffix Normalization

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | First Name, Last Name |
| **Type** | Business |
| **Configurable** | Yes — strip vs. keep, and target format |
| **Default Enabled** | No |
| **Dependencies** | CLN-001, CLN-002 |

**Purpose:** Handle suffixes (`Jr.`, `III`, `PhD`) that sometimes leak into
name fields, without silently discarding information some campaigns
deliberately want kept for personalization.

**Rule Description:** Detects a configurable set of suffix patterns
trailing a name field. If configured to strip, removes the suffix from the
name value and records it separately (never simply discarded) as a derived
attribute. If configured to keep, the field is left unchanged and this rule
is effectively a no-op that still gets logged/metered.

**Input Example:** `"Robert Smith III"` (Last Name field) → **Output Example (strip mode):** `"Smith"` (suffix `"III"` retained as a separate derived value, not deleted)

**Potential Risks:** Default is off specifically because stripping is a
judgment call some outreach use cases actively don't want; a wrong default
could silently remove personalization value from names.

**Test Cases:**
- Given `"Smith III"` with strip enabled, expect name `"Smith"` and suffix `"III"` captured.
- Given `"Smith III"` with the rule disabled, expect `"Smith III"` unchanged.
- Given `"O'Brien"` (no suffix present), expect no change and no suffix captured.

---

#### CLN-004 — Title Acronym Casing Correction

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | Title |
| **Type** | Business |
| **Configurable** | Yes — acronym dictionary is user-supplied reference data |
| **Default Enabled** | Yes — fixes a specific, evidenced defect (see Purpose) |
| **Dependencies** | CLN-001 |

**Purpose:** Directly corrects a defect observed in the reference dataset,
where the source system's own title-casing turned acronyms like "CRM" into
"Crm" (e.g., *"Div. Vice President Of R&D - Crm"*).

**Rule Description:** Matches whole-word tokens within `Title` against a
configurable acronym dictionary (e.g., CRM, VP, CFO, R&D, IT) and replaces
each match with its correctly-cased form, leaving all other tokens untouched.

**Input Example:** `"Director, Crm Product Development"` → **Output Example:** `"Director, CRM Product Development"`

**Potential Risks:** An acronym dictionary that's too aggressive could
"correct" a word that isn't actually meant as that acronym in context (low
likelihood for well-chosen entries like CRM/VP, but real for shorter/more
ambiguous tokens); keep the dictionary curated and reviewed, not
auto-expanding.

**Test Cases:**
- Given `"Chief Crm Officer"`, expect `"Chief CRM Officer"`.
- Given `"Svp - Relationship Manager"`, expect `"SVP - Relationship Manager"`.
- Given `"Vice President Of R&D"` (already correct), expect no change.
- Given a title containing no dictionary acronyms, expect no change.

---

#### CLN-005 — Title Abbreviation Expansion/Contraction

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | Title |
| **Type** | Business |
| **Configurable** | Yes — direction (expand vs. contract) and mapping table |
| **Default Enabled** | No |
| **Dependencies** | CLN-001, CLN-004 |

**Purpose:** Let an organization standardize on either fully-spelled-out or
abbreviated title conventions, since both are legitimate and neither is
objectively correct.

**Rule Description:** Applies a configurable mapping table in the
configured direction — e.g., `"Sr."` → `"Senior"` (expand) or the reverse
(contract) — matching whole tokens only.

**Input Example (expand mode):** `"Sr. Director"` → **Output Example:** `"Senior Director"`

**Potential Risks:** Off by default because it's purely a style preference;
an org that wants no change at all must simply never enable it — there's no
"neutral" default that satisfies every convention.

**Test Cases:**
- Given `"Sr. Director"` with expand mode, expect `"Senior Director"`.
- Given `"Senior Director"` with contract mode, expect `"Sr. Director"`.
- Given the rule disabled, expect no change regardless of content.

---

#### CLN-006 — Missing Name Warning

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | First Name, Last Name |
| **Type** | Warning |
| **Configurable** | Yes — enable/disable only (no threshold) |
| **Default Enabled** | Yes |
| **Dependencies** | Runs after all Identity Business rules (Warning stage) |

**Purpose:** Surface records missing a core identity field, since a lead
without a name is of limited use to downstream outreach personalization.

**Rule Description:** Raises a warning if `First Name` or `Last Name` is
absent (`None` or empty after normalization). Does not block the pipeline
or alter the record.

**Input Example:** `First Name = None` → **Output Example:** Warning
`MISSING_FIRST_NAME` attached to the record; field itself unchanged.

**Potential Risks:** None — purely observational.

**Test Cases:**
- Given `First Name = None`, expect a `MISSING_FIRST_NAME` warning.
- Given `Last Name = ""`, expect a `MISSING_LAST_NAME` warning.
- Given both fields populated, expect no warning.

---

#### CLN-007 — Identical First/Last Name Warning

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | First Name, Last Name |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-001, CLN-002 |

**Purpose:** Flag a plausible data-entry or column-mapping error.

**Rule Description:** Raises a warning if `First Name` equals `Last Name`
(case-insensitive) after normalization.

**Input Example:** `First Name = "Taylor"`, `Last Name = "Taylor"` → **Output Example:** Warning `IDENTICAL_FIRST_LAST_NAME`.

**Potential Risks:** Low false-positive risk exists for genuinely identical
legal first/last names (rare but real); this must remain a warning, never a rejection.

**Test Cases:**
- Given `First Name = "Taylor"`, `Last Name = "Taylor"`, expect the warning.
- Given `First Name = "taylor"`, `Last Name = "Taylor"` (case difference only), expect the warning (case-insensitive comparison).
- Given differing names, expect no warning.

---

#### CLN-008 — Name Contains Unexpected Characters Warning

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | First Name, Last Name |
| **Type** | Warning |
| **Configurable** | Yes — character-class pattern |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-001 |

**Purpose:** Catch likely data corruption or column misalignment (e.g., a
name field containing digits).

**Rule Description:** Raises a warning if the field contains digits or
symbols outside an allow-list of characters expected in names (letters,
spaces, hyphens, apostrophes, and common diacritics).

**Input Example:** `"John123"` → **Output Example:** Warning `UNEXPECTED_CHARACTERS_IN_NAME`.

**Potential Risks:** Legitimate names using less-common scripts/characters
could false-positive if the allow-list is too narrow; the pattern must be
configurable per locale.

**Test Cases:**
- Given `"John123"`, expect the warning.
- Given `"José"`, expect no warning (diacritic allowed).
- Given `"O'Brien-Smith"`, expect no warning (apostrophe/hyphen allowed).

---

#### CLN-009 — Title Unusually Long Warning

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | Title |
| **Type** | Warning |
| **Configurable** | Yes — length threshold |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-001 |

**Purpose:** Catch likely glued-together or misaligned text (e.g., a title
column that accidentally absorbed a business description).

**Rule Description:** Raises a warning if `Title` exceeds a configurable
character-length threshold (default: 100 characters — chosen comfortably
above the longest legitimate title observed during dataset profiling, ~122 characters, with margin for review rather than as a hard cutoff).

**Input Example:** A 250-character string → Warning `TITLE_UNUSUALLY_LONG`.

**Potential Risks:** Some genuinely long, hyphenated titles exist (observed
up to 122 characters in profiling); threshold must stay comfortably above
observed legitimate maxima to avoid noise.

**Test Cases:**
- Given a 50-character title, expect no warning.
- Given a 150-character title, expect the warning.
- Given the threshold reconfigured to 200, expect the same 150-character title to raise no warning.

---

#### CLN-010 — Contact Level / Title Inconsistency Warning

| | |
|---|---|
| **Category** | Identity |
| **Field(s)** | Contact Level, Title |
| **Type** | Warning |
| **Configurable** | Yes — keyword mapping table, and enable/disable |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-001, CLN-004 |

**Purpose:** Surface a soft, explainable signal that two related fields may
disagree — useful triage information, not an authoritative judgment.

**Rule Description:** Checks whether `Title` contains at least one keyword
consistent with the stated `Contact Level` (e.g., Contact Level = "C-Level"
expects a keyword like "Chief" or a "C**O" pattern in the title). Raises a
low-confidence warning if no consistent keyword is found. Explicitly
labeled as heuristic in the warning message itself.

**Input Example:** `Contact Level = "C-Level"`, `Title = "Regional Sales Manager"` → Warning `CONTACT_LEVEL_TITLE_MISMATCH`.

**Potential Risks:** Real-world title phrasing is too varied for this check
to be authoritative; must always be presented as a low-confidence signal,
never as a validation failure, to avoid engineers or downstream automation
treating it as ground truth.

**Test Cases:**
- Given `Contact Level = "C-Level"`, `Title = "Chief Experience Officer"`, expect no warning.
- Given `Contact Level = "C-Level"`, `Title = "Regional Sales Manager"`, expect the warning.
- Given `Contact Level` empty, expect no warning (nothing to compare against).

---

### 9.2 Contact

*Fields: `Email`, `Company Email`, `Email usage restriction`, `Direct Phone`, `Direct phone usage restriction`, `Phone`, `Fax`*

#### CLN-011 — Trim & Normalize Whitespace (Email Fields)

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email, Company Email |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Remove whitespace noise, which is never semantically meaningful
inside an email address.

**Rule Description:** Removes all whitespace (leading, trailing, and
internal — unlike name fields, an email legitimately never contains an
internal space) and applies Unicode NFC normalization.

**Input Example:** `" cristinaf@justfoodfordogs.com "` → **Output Example:** `"cristinaf@justfoodfordogs.com"`

**Potential Risks:** None — no valid email contains whitespace anywhere.

**Test Cases:**
- Given `" a@b.com "`, expect `"a@b.com"`.
- Given `"a @b.com"` (internal space), expect `"a@b.com"`.
- Given `None`, expect `None` unchanged.

---

#### CLN-012 — Strip Phone Force-Text Artifact

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Direct Phone, Phone, Fax |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Remove a spreadsheet-software artifact, observed on 100% of
populated `Direct Phone` values in the reference dataset, that is not part
of the phone number itself.

**Rule Description:** Strips a leading straight-apostrophe character
(`'`) if present — Excel's own mechanism for forcing a numeric-looking cell
to be treated as text. This character is never part of a real phone number;
removing it is the same class of operation as stripping a byte-order mark.

**Input Example:** `"'+19497849202"` → **Output Example:** `"+19497849202"`

**Potential Risks:** None — this exact artifact was directly observed and
confirmed to be a formatting marker, not data, during Import Engine profiling.

**Test Cases:**
- Given `"'+19497849202"`, expect `"+19497849202"`.
- Given `"+19497849202"` (no artifact present), expect no change.
- Given `"'"` alone (edge case), expect `""`.

---

#### CLN-013 — Email Domain Lowercasing

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email, Company Email |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011 |

**Purpose:** Normalize the one part of an email address that is
*guaranteed* case-insensitive by specification (DNS hostnames, RFC 1035),
independent of any policy choice about the local part.

**Rule Description:** Lowercases only the portion of the address after the
`@` symbol; the local part (before `@`) is left untouched by this rule.

**Input Example:** `"Cristinaf@JustFoodForDogs.COM"` → **Output Example:** `"Cristinaf@justfoodfordogs.com"`

**Potential Risks:** None — this is guaranteed safe by the DNS specification, not a judgment call.

**Test Cases:**
- Given `"User@EXAMPLE.COM"`, expect `"User@example.com"`.
- Given `"user@example.com"` (already lowercase), expect no change.
- Given an address with no `@` (malformed), expect no change — this rule does not attempt to fix malformed input, only normalize a well-formed domain (see CLN-019 for the corresponding warning).

---

#### CLN-014 — Email Local-Part Lowercasing

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email, Company Email |
| **Type** | Business |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-013 |

**Purpose:** Provide one consistent, comparable email representation for
matching/deduplication use cases, acknowledging this is a policy choice, not
a specification guarantee.

**Rule Description:** Lowercases the local part (before `@`) of the email
address. Unlike CLN-013, this is *not* guaranteed safe by any RFC — RFC 5321
technically permits a case-sensitive local part — but is near-universal
practice among real mail providers.

**Input Example:** `"CristinaF@justfoodfordogs.com"` → **Output Example:** `"cristinaf@justfoodfordogs.com"`

**Potential Risks:** In the rare case a mail server genuinely treats the
local part as case-sensitive, this normalization could theoretically produce
an address that doesn't match the original mailbox. Documented as a known,
accepted, opt-out-able tradeoff, not silently assumed.

**Test Cases:**
- Given `"CristinaF@example.com"`, expect `"cristinaf@example.com"`.
- Given the rule disabled, expect the local part unchanged while CLN-013 still lowercases the domain.

---

#### CLN-015 — Primary Email Selection

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email, Company Email (reads both; writes a new derived attribute) |
| **Type** | Business |
| **Configurable** | Yes — priority order |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-013, CLN-014 |

**Purpose:** Give downstream consumers one unambiguous "which email do I
use" answer when a record has both an `Email` and a `Company Email`,
**without discarding either original value.**

**Rule Description:** Derives a new `primary_email` attribute pointing to
one of the two source fields, per a configurable priority order (default:
`Email` before `Company Email`). Both original fields remain present,
untouched, in the cleaned record — this rule is purely additive.

**Input Example:** `Email = "cristinaf@justfoodfordogs.com"`, `Company Email = None` → **Output Example:** `primary_email = "cristinaf@justfoodfordogs.com"`; both source fields unchanged.

**Potential Risks:** If implemented incorrectly, could be mistaken for a
rule that *drops* the non-primary field — must be explicit in code and
documentation that it only derives a pointer, never deletes data.

**Test Cases:**
- Given only `Email` populated, expect `primary_email` to equal it.
- Given both populated, expect `primary_email` to follow the configured priority order.
- Given neither populated, expect `primary_email = None` (and CLN-018 fires separately).

---

#### CLN-016 — Phone Number Canonical Formatting (E.164)

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Direct Phone, Phone |
| **Type** | Business |
| **Configurable** | Yes — requires an explicit default region; no implicit default |
| **Default Enabled** | No — requires explicit configuration before use |
| **Dependencies** | CLN-011, CLN-012 |

**Purpose:** Produce one consistent, machine-comparable phone representation.

**Rule Description:** Reformats a phone number into E.164
(`+<countrycode><number>`, e.g., `+19497223647`). When no country code is
present in the source value, a configured default region is applied — the
profile must set this explicitly; there is no silent global default,
because assuming "US" would silently corrupt a future international
dataset the same way an unstated assumption elsewhere in this project
already caused real data loss.

**Input Example (US default region configured):** `"1-949-722-3647"` → **Output Example:** `"+19497223647"`

**Potential Risks:** Wrong default-region configuration silently produces
plausible-looking but incorrect numbers. Mitigation: this rule is Disabled
by default and its configuration is validated at profile-load time —
enabling it without a configured region should raise
`InvalidCleaningConfigurationError` rather than guessing.

**Test Cases:**
- Given `"1-949-722-3647"` with US default region, expect `"+19497223647"`.
- Given `"+19497223647"` (already E.164), expect no change.
- Given the rule enabled with no default region configured, expect the pipeline to fail fast at configuration-load time, before any record is processed.

---

#### CLN-017 — Primary Phone Selection

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Direct Phone, Phone (reads both; writes a derived attribute) |
| **Type** | Business |
| **Configurable** | Yes — priority order |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-012 |

**Purpose:** Same rationale as CLN-015, applied to phone numbers.

**Rule Description:** Derives a `primary_phone` attribute per a configurable
priority order (default: `Direct Phone` before `Phone`), purely additive —
both source fields remain untouched.

**Input Example:** `Direct Phone = "+19497849202"`, `Phone = "1-949-722-3647"` → **Output Example:** `primary_phone = "+19497849202"`.

**Potential Risks:** Same as CLN-015 — must never be implemented as a
value-dropping rule.

**Test Cases:**
- Given only `Phone` populated, expect `primary_phone` to equal it.
- Given both populated, expect the configured priority order to be respected.
- Given neither populated, expect `primary_phone = None`.

---

#### CLN-018 — Missing Email Warning

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | Warning stage (runs after normalization) |

**Purpose:** Surface leads with no email contact method.

**Rule Description:** Raises a warning if `Email` is absent after
normalization. Does not consider `Company Email` a substitute (that's
CLN-015's job, which is additive and doesn't change whether this warning fires).

**Input Example:** `Email = None` → Warning `MISSING_EMAIL`.

**Potential Risks:** None — observational only.

**Test Cases:**
- Given `Email = None`, expect the warning.
- Given `Email` populated, expect no warning, regardless of `Company Email`.

---

#### CLN-019 — Malformed Email Shape Warning

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email, Company Email |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-013, CLN-014 |

**Purpose:** Flag values that don't look syntactically like an email —
**a shape check, not a mailbox-existence claim** (that's Verification
Engine's job, out of scope here).

**Rule Description:** Raises a warning if the value contains no `@`, more
than one `@`, or the domain portion contains no `.`.

**Input Example:** `"cristinaf.justfoodfordogs.com"` (no `@`) → Warning `MALFORMED_EMAIL_SHAPE`.

**Potential Risks:** Deliberately conservative (checks only the most basic
shape signals) to avoid false-positiving on the wide variety of technically
valid but unusual real email formats; not intended to be a full RFC 5322 validator.

**Test Cases:**
- Given `"a.example.com"` (no `@`), expect the warning.
- Given `"a@b@c.com"` (two `@` symbols), expect the warning.
- Given `"a@localhost"` (no `.` in domain), expect the warning.
- Given `"a@example.com"`, expect no warning.

---

#### CLN-020 — Role-Based Email Pattern Warning

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Email |
| **Type** | Warning |
| **Configurable** | Yes — pattern list |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-013, CLN-014 |

**Purpose:** Surface a useful signal for a B2B outreach platform: generic
inboxes (`info@`, `sales@`, `noreply@`) behave differently from personal
ones and often warrant different outreach handling.

**Rule Description:** Raises a warning if the local part matches a
configurable list of role-based prefixes.

**Input Example:** `"info@acmecorp.com"` → Warning `ROLE_BASED_EMAIL_PATTERN`.

**Potential Risks:** Pattern list is inherently incomplete; false negatives
(a role-based address not on the list) are more likely than false positives
and are an acceptable tradeoff for a non-blocking, informational signal.

**Test Cases:**
- Given `"info@acmecorp.com"`, expect the warning.
- Given `"cristinaf@justfoodfordogs.com"`, expect no warning.
- Given a custom pattern list including `"team@"`, expect `"team@acmecorp.com"` to raise the warning.

---

#### CLN-021 — Missing Phone Warning

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Direct Phone, Phone |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | Warning stage |

**Purpose:** Surface leads with no phone contact method, mirroring CLN-018 for phones.

**Rule Description:** Raises a warning if both `Direct Phone` and `Phone`
are absent after normalization.

**Input Example:** Both fields `None` → Warning `MISSING_PHONE`.

**Potential Risks:** None.

**Test Cases:**
- Given both fields empty, expect the warning.
- Given either field populated, expect no warning.

---

#### CLN-022 — Implausible Phone Digit Count Warning

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Direct Phone, Phone |
| **Type** | Warning |
| **Configurable** | Yes — minimum digit threshold |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-012 |

**Purpose:** Flag values unlikely to be a real phone number by digit count
alone — a shape check, not a reachability claim.

**Rule Description:** Strips all non-digit characters and raises a warning
if fewer than a configurable minimum (default: 7) digits remain.

**Input Example:** `"555-1234x"` stripped to `"5551234"` = 7 digits → no
warning at default threshold; `"555-12"` stripped to `"55512"` = 5 digits → Warning `IMPLAUSIBLE_PHONE_DIGIT_COUNT`.

**Potential Risks:** Minimum digit plausibility varies by country numbering
plan; threshold must remain configurable rather than fixed for a
multi-country dataset.

**Test Cases:**
- Given `"+19497849202"` (11 digits), expect no warning.
- Given `"555-12"` (5 digits), expect the warning at the default threshold.
- Given the threshold reconfigured to 5, expect `"555-12"` to raise no warning.

---

#### CLN-023 — Phone Contains Non-Numeric Characters Warning

| | |
|---|---|
| **Category** | Contact |
| **Field(s)** | Direct Phone, Phone |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-011, CLN-012 |

**Purpose:** Flag values containing letters (e.g., vanity numbers like
"1-800-FLOWERS") for review, without silently discarding or "fixing" them.

**Rule Description:** Raises a warning if the value (after stripping known
formatting characters: spaces, dashes, parentheses, `+`) still contains
alphabetic characters.

**Input Example:** `"1-800-FLOWERS"` → Warning `PHONE_CONTAINS_LETTERS`.

**Potential Risks:** Vanity numbers may be intentional and valid; this rule
must never trigger any modification, only a flag for human review.

**Test Cases:**
- Given `"1-800-FLOWERS"`, expect the warning.
- Given `"+19497849202"`, expect no warning.

---

### 9.3 Company

*Fields: `Company Name`, `Tradestyle`, `Ownership Type`, `D&B Legal Status Type`, `Entity Type`, `Is Headquarters`, `Ticker`, `Parent Company`, `Parent Country/Region`, `Global Ultimate Company`, `Global Ultimate Country/Region`, `Business Description`, `D-U-N-S® Number`, `Key ID`*

#### CLN-024 — Trim & Normalize Whitespace (Company Text Fields)

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Company Name, Tradestyle, Ownership Type, Entity Type, Parent Company, Global Ultimate Company, Business Description |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Baseline text hygiene for this category, including the
long-form `Business Description` field, where stray control characters are
most likely to hide.

**Rule Description:** Trims/collapses whitespace, applies Unicode NFC
normalization, strips control characters.

**Input Example:** `"Abbott  Laboratories\t"` → **Output Example:** `"Abbott Laboratories"`

**Potential Risks:** None.

**Test Cases:**
- Given `" Adobe Inc.  "`, expect `"Adobe Inc."`.
- Given a `Business Description` with an embedded tab character, expect it removed.

---

#### CLN-025 — D-U-N-S Number Whitespace-Only Trim

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | D-U-N-S® Number |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Apply the minimum possible cleaning to an identifier field, by
design — internal characters (including leading zeros) are never touched.

**Rule Description:** Trims only leading/trailing whitespace. **Does not**
reformat, reflow, re-type, or otherwise alter internal characters. This rule
exists as its own explicit entry — separate from CLN-024 — specifically
because identifiers carry a stricter guarantee than ordinary text fields,
and that guarantee deserves its own auditable rule rather than being
implicit in a general text-cleanup rule.

**Input Example:** `" 036611498 "` → **Output Example:** `"036611498"` (leading zero intact)

**Potential Risks:** None, provided this rule is never merged with a
general-purpose text rule that might apply casing or other transforms.

**Test Cases:**
- Given `" 036611498 "`, expect `"036611498"` with the leading zero preserved.
- Given `"036611498"` (already trimmed), expect no change.

---

#### CLN-026 — Legal Suffix Standardization

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Company Name |
| **Type** | Business |
| **Configurable** | Yes — canonical form, or strip entirely |
| **Default Enabled** | No |
| **Dependencies** | CLN-024 |

**Purpose:** Support matching/deduplication use cases that want a
normalized company name, while respecting that other use cases want the
exact legal name preserved as-is.

**Rule Description:** Standardizes legal-entity suffixes ("Inc", "Inc.",
"Incorporated") to one configured canonical form, or strips them entirely
if configured to do so. Writes the result to a derived attribute
(`company_name_normalized`), never overwriting the original `Company Name`.

**Input Example:** `"Abercrombie & Fitch Co."` (strip mode) → **Output Example:** `company_name_normalized = "Abercrombie & Fitch"`; `Company Name` unchanged.

**Potential Risks:** Genuinely lossy by design (that's why it writes to a
derived field rather than overwriting); stripping "Inc." can occasionally
collide two legally distinct entities under one normalized name.

**Test Cases:**
- Given `"Adobe Inc."` with strip mode, expect `company_name_normalized = "Adobe"`; `Company Name` unchanged.
- Given the rule disabled, expect no `company_name_normalized` attribute produced.

---

#### CLN-027 — Company Name Casing Standardization

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Company Name |
| **Type** | Business |
| **Configurable** | Yes — exception list is user-supplied reference data |
| **Default Enabled** | No — unbounded, idiosyncratic brand-name capitalization makes this materially riskier than CLN-002's name casing, which has a well-bounded exception set |
| **Dependencies** | CLN-024 |

**Purpose:** Optionally provide display-consistent company name casing for
organizations that want it, while defaulting off given real risk.

**Rule Description:** Applies Title Case except for entries matching a
configurable exception list of known stylized brand capitalizations
(e.g., "eBay," "iHeartMedia," "PwC").

**Input Example:** `"EBAY INC."` (exception list includes "eBay") → **Output Example:** `"eBay Inc."`

**Potential Risks:** The highest-risk casing rule in the registry — an
incomplete exception list produces visibly wrong, unprofessional-looking
output in outreach (e.g., "Ebay" instead of "eBay"). This is precisely why
it defaults off, unlike CLN-002.

**Test Cases:**
- Given `"ADOBE INC."` with no matching exception, expect `"Adobe Inc."`.
- Given `"EBAY INC."` with "eBay" in the exception list, expect `"eBay Inc."`.
- Given the rule disabled, expect no change.

---

#### CLN-028 — Boolean Flag Representation Normalization (Is Headquarters)

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Is Headquarters |
| **Type** | Business |
| **Configurable** | Yes — source representation mapping |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Ensure a native boolean regardless of how a given source
represents true/false — the current Excel adapter already returns a native
`bool`, but future CSV/SQL sources may hand back `"Y"/"N"` or `"1"/"0"` strings.

**Rule Description:** Maps a configurable set of source string
representations to native boolean `True`/`False`. Values already native
booleans pass through unchanged.

**Input Example (future CSV source):** `"Y"` → **Output Example:** `True`

**Potential Risks:** Low — the main risk is an incomplete mapping table for
an unanticipated source representation, which should raise a warning (not
silently guess) if a value doesn't match any configured mapping.

**Test Cases:**
- Given a native `False`, expect no change.
- Given `"Y"` with the mapping configured, expect `True`.
- Given an unmapped string value, expect the value left unchanged and a mapping-gap warning raised.

---

#### CLN-029 — Missing Company Name Warning

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Company Name |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | Warning stage |

**Purpose:** A lead without a company name is severely limited for a B2B platform.

**Rule Description:** Raises a warning if `Company Name` is absent after normalization.

**Input Example:** `Company Name = None` → Warning `MISSING_COMPANY_NAME`.

**Potential Risks:** None.

**Test Cases:**
- Given `Company Name = None`, expect the warning.
- Given it populated, expect no warning.

---

#### CLN-030 — Company Name Equals Parent Company Warning

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Company Name, Parent Company |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-024 |

**Purpose:** Purely informational — useful context, not a defect.

**Rule Description:** Raises a warning if `Company Name` equals `Parent
Company` (case-insensitive) after normalization.

**Input Example:** Both = `"U.S. Bancorp"` → Warning `COMPANY_EQUALS_PARENT`.

**Potential Risks:** None — this is common and expected for standalone
companies with no parent; kept as informational, never treated as an error.

**Test Cases:**
- Given identical values, expect the warning.
- Given a genuine parent/subsidiary pair, expect no warning.

---

#### CLN-031 — Ticker Present Without Public Ownership Warning

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Ticker, Ownership Type |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-024 |

**Purpose:** Soft cross-field consistency check within the Company category.

**Rule Description:** Raises a warning if `Ticker` is populated but
`Ownership Type` doesn't contain a value indicating public ownership
(e.g., contains "Private" or "Partnership" only, without "Public").

**Input Example:** `Ticker = "ABC"`, `Ownership Type = "Private"` → Warning `TICKER_WITHOUT_PUBLIC_OWNERSHIP`.

**Potential Risks:** `Ownership Type` values observed in profiling are
comma-separated multi-value strings (e.g., "Private, Public, Partnership");
the check must handle multi-value fields correctly, not assume a single value.

**Test Cases:**
- Given `Ticker = "ABC"`, `Ownership Type = "Private"`, expect the warning.
- Given `Ticker = "ABC"`, `Ownership Type = "Private, Public, Partnership"`, expect no warning (Public present among values).
- Given `Ticker` empty, expect no warning regardless of `Ownership Type`.

---

#### CLN-032 — Business Description Suspiciously Short Warning

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Business Description |
| **Type** | Warning |
| **Configurable** | Yes — length threshold |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-024 |

**Purpose:** Catch likely placeholder values ("N/A," "-") rather than a genuine description.

**Rule Description:** Raises a warning if the field is populated but its
length is below a configurable threshold (default: 10 characters).

**Input Example:** `"N/A"` (3 characters) → Warning `BUSINESS_DESCRIPTION_SUSPICIOUSLY_SHORT`.

**Potential Risks:** Low; threshold is deliberately small to avoid flagging
legitimately terse but real descriptions.

**Test Cases:**
- Given `"N/A"`, expect the warning.
- Given a full paragraph description, expect no warning.
- Given the field empty (not just short), expect no warning from this rule (that's a separate "missing" concern, not modeled here since `Business Description` is optional enrichment, not a core field).

---

#### CLN-033 — D-U-N-S Number Shape Warning

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | D-U-N-S® Number |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-025 |

**Purpose:** Flag values that don't match the expected shape of a D-U-N-S
number — **a pattern check only, not a claim the number is registered/real**
(that would be verification, out of scope).

**Rule Description:** Raises a warning if, after CLN-025's whitespace trim,
the value is not exactly 9 numeric digits.

**Input Example:** `"36611498"` (8 digits — the exact corruption pattern
found when this field was mishandled by a numeric-inference library during
Import Engine profiling) → Warning `DUNS_SHAPE_UNEXPECTED`.

**Potential Risks:** None for the check itself; its main value is as a
tripwire that would have caught the original leading-zero bug had it existed
downstream of a less careful import.

**Test Cases:**
- Given `"036611498"` (9 digits), expect no warning.
- Given `"36611498"` (8 digits), expect the warning.
- Given a non-numeric value, expect the warning.

---

#### CLN-034 — Key ID Missing Warning

| | |
|---|---|
| **Category** | Company |
| **Field(s)** | Key ID |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Informational — `Key ID` is the company-level identifier
confirmed during profiling to correlate 1:1 with distinct companies in the
reference dataset; its absence is worth surfacing.

**Rule Description:** Raises a warning if `Key ID` is absent.

**Input Example:** `Key ID = None` → Warning `MISSING_KEY_ID`.

**Potential Risks:** None.

**Test Cases:**
- Given `Key ID = None`, expect the warning.
- Given it populated, expect no warning.

---

### 9.4 Address

*Fields: `Address Line 1`, `Address Line 2`, `Address Line 3`, `City`, `State Or Province`, `Postal Code`, `Country/Region`*

#### CLN-035 — Trim & Normalize Whitespace (Address Fields)

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Address Line 1, Address Line 2, Address Line 3, City, State Or Province, Postal Code, Country/Region |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Baseline text hygiene, as in every other category.

**Rule Description:** Trims/collapses whitespace, Unicode NFC normalization, strips control characters.

**Input Example:** `"  New York "` → **Output Example:** `"New York"`

**Potential Risks:** None.

**Test Cases:**
- Given `" 92782-1838 "`, expect `"92782-1838"`.
- Given `""`, expect `""` unchanged.

---

#### CLN-036 — Normalize Empty Address Line Representation

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Address Line 1, Address Line 2, Address Line 3 |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-035 |

**Purpose:** Ensure "nothing here" is represented one consistent way,
regardless of whether the source used an empty string or a genuinely absent
cell — this changes *representation only*, never content.

**Rule Description:** Converts an empty string (post-trim) to the same
canonical absent-value marker used for a truly missing cell.

**Input Example:** `""` → **Output Example:** `None`

**Potential Risks:** None — purely a representational normalization of
already-absent data.

**Test Cases:**
- Given `""`, expect `None`.
- Given `None` (already absent), expect `None` unchanged.
- Given `"Suite 400"` (real content), expect no change.

---

#### CLN-037 — State/Province Standardization

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | State Or Province |
| **Type** | Business |
| **Configurable** | Yes — target format (abbreviation vs. full name); reference table is user-supplied |
| **Default Enabled** | No |
| **Dependencies** | CLN-035 |

**Purpose:** Support consistent state representation for organizations that
want it, acknowledging both abbreviation and full-name conventions are
legitimate and neither is universally correct.

**Rule Description:** Maps the value against a configurable reference table
to the configured target format.

**Input Example (target = abbreviation):** `"California"` → **Output Example:** `"CA"`

**Potential Risks:** A reference table gap (an unrecognized state/province
name, more likely for non-US regions) leaves the value unchanged and should
raise a mapping-gap signal rather than silently failing.

**Test Cases:**
- Given `"California"` with target=abbreviation, expect `"CA"`.
- Given `"CA"` with target=full name, expect `"California"`.
- Given a value not in the reference table, expect it left unchanged plus a mapping-gap signal.

---

#### CLN-038 — Country Standardization (ISO 3166)

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Country/Region |
| **Type** | Business |
| **Configurable** | Yes — target format (alpha-2 vs. alpha-3 vs. full name) |
| **Default Enabled** | No |
| **Dependencies** | CLN-035 |

**Purpose:** Same rationale as CLN-037, applied to country.

**Rule Description:** Maps the value against a configurable ISO 3166
reference table to the configured target format.

**Input Example (target = alpha-2):** `"United States"` → **Output Example:** `"US"`

**Potential Risks:** Same reference-table-gap risk as CLN-037.

**Test Cases:**
- Given `"United States"` with target=alpha-2, expect `"US"`.
- Given `"US"` with target=full name, expect `"United States"`.
- Given an unrecognized value, expect it unchanged plus a mapping-gap signal.

---

#### CLN-039 — Postal Code Formatting Policy

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Postal Code |
| **Type** | Business |
| **Configurable** | Yes — target format (5-digit / ZIP+4 / as-is) |
| **Default Enabled** | No — the ZIP+4 → 5-digit direction is lossy by choice and must never be a silent default |
| **Dependencies** | CLN-035 |

**Purpose:** Let an organization standardize postal code format for its
own downstream systems, while making the lossy option explicit and opt-in only.

**Rule Description:** Reformats to the configured target. Truncating
ZIP+4 to 5 digits discards real information (the +4 extension) and is only
performed when explicitly configured to do so.

**Input Example (target = 5-digit):** `"92782-1838"` → **Output Example:** `"92782"`

**Potential Risks:** The 5-digit target is intentionally lossy; this rule
exists specifically to make that loss a deliberate, visible, opt-in choice
rather than an accident of some other rule's side effect.

**Test Cases:**
- Given `"92782-1838"` with target=as-is, expect no change.
- Given `"92782-1838"` with target=5-digit, expect `"92782"`.
- Given `"92782"` with target=ZIP+4, expect no change (nothing to add — this rule never invents a +4 extension that isn't in the source).

---

#### CLN-040 — Street Abbreviation Standardization

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Address Line 1 |
| **Type** | Business |
| **Configurable** | Yes — reference table is region-aware, not hardcoded to one country's conventions |
| **Default Enabled** | No |
| **Dependencies** | CLN-035 |

**Purpose:** Support consistent street-suffix formatting, while explicitly
avoiding the trap of assuming US conventions apply to every dataset.

**Rule Description:** Maps street-type tokens ("Street" ↔ "St.") against a
configurable, region-scoped reference table, selected based on the record's
own `Country/Region` — not a single global table.

**Input Example (US region, target = abbreviated):** `"123 Main Street"` → **Output Example:** `"123 Main St."`

**Potential Risks:** Highest risk in the Address category for
over-generalizing a US-centric convention onto non-US addresses; the
region-scoping requirement exists specifically to prevent that.

**Test Cases:**
- Given a US address with target=abbreviated, expect `"Street"` → `"St."`.
- Given a non-US address, expect no US-specific abbreviation applied unless a matching region-specific table exists.
- Given the rule disabled, expect no change.

---

#### CLN-041 — Incomplete Address Component Warning

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | City, State Or Province, Postal Code |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-035, CLN-036 |

**Purpose:** Surface a plausible data-quality gap: some but not all address components present.

**Rule Description:** Raises a warning if exactly one or two (not zero, not
all three) of `City`, `State Or Province`, `Postal Code` are populated.

**Input Example:** `City = "Austin"`, `State Or Province = None`, `Postal Code = "78727"` → Warning `INCOMPLETE_ADDRESS_COMPONENTS`.

**Potential Risks:** None — purely observational; zero-of-three and
three-of-three are both considered consistent states and don't trigger this warning.

**Test Cases:**
- Given all three populated, expect no warning.
- Given all three empty, expect no warning (a fully absent address is a different concern, not "incomplete").
- Given exactly one populated, expect the warning.

---

#### CLN-042 — Postal Code Shape Warning

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Postal Code, Country/Region |
| **Type** | Warning |
| **Configurable** | Yes — per-country pattern table |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-035 |

**Purpose:** Flag postal codes with an unexpected shape for their stated
country — a pattern check, not a deliverability claim.

**Rule Description:** Checks the value's length/pattern against a
configurable, per-country expectation table (e.g., US: 5 or 9 digits).
Countries without a configured pattern are skipped, not flagged.

**Input Example:** `Country/Region = "United States"`, `Postal Code = "AB1"` → Warning `POSTAL_CODE_SHAPE_UNEXPECTED`.

**Potential Risks:** Requires a maintained per-country pattern table;
absent an entry for a given country, this rule must skip silently rather
than guess or apply a wrong pattern.

**Test Cases:**
- Given a US address with a 5-digit postal code, expect no warning.
- Given a US address with `"AB1"`, expect the warning.
- Given a country with no configured pattern, expect no warning (skipped, not guessed).

---

#### CLN-043 — Address Line Duplicate Content Warning

| | |
|---|---|
| **Category** | Address |
| **Field(s)** | Address Line 1, City |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-035 |

**Purpose:** Catch a plausible column-misalignment error within the Address category itself.

**Rule Description:** Raises a warning if `Address Line 1` equals `City`
(case-insensitive) after normalization.

**Input Example:** `Address Line 1 = "Austin"`, `City = "Austin"` → Warning `ADDRESS_LINE_DUPLICATES_CITY`.

**Potential Risks:** Low false-positive risk for unusual but real cases
(a street literally named after the city); kept as informational only.

**Test Cases:**
- Given identical values, expect the warning.
- Given distinct values, expect no warning.

---

### 9.5 Financial

*Fields: `Sales (USD)`, `Pre Tax Profit (USD)`, `Assets (USD)`, `Liabilities (USD)`, `Employees (Single Site)`, `Employees (Total)`*

#### CLN-044 — Normalize Missing-Value Representation (Financial Fields)

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Sales (USD), Pre Tax Profit (USD), Assets (USD), Liabilities (USD), Employees (Single Site), Employees (Total) |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** These fields arrive already correctly typed (float/int) from
the Import Engine, per prior profiling — the only legitimate lossless
operation left is standardizing how "absent" is represented across sources
that might encode it differently (empty cell vs. a null-like sentinel string).

**Rule Description:** Normalizes any recognized "absent" sentinel to the
platform's single canonical missing-value marker. **Never touches a present
numeric value** — this rule cannot alter a number, only standardize the
representation of its absence.

**Input Example:** A future CSV source's `"N/A"` sentinel → **Output Example:** canonical missing marker (`None`)

**Potential Risks:** None for present values; a risk only if the sentinel
list is misconfigured to match a legitimate value (mitigated by keeping the
sentinel list narrow and explicit, e.g., `"N/A"`, `"NULL"`, never a bare `"0"`).

**Test Cases:**
- Given a native float value, expect no change.
- Given `"N/A"` from a text-based source, expect the canonical missing marker.
- Given `0` (a real zero), expect it preserved as `0`, never treated as missing.

---

#### CLN-045 — Currency Unit Tagging

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Sales (USD), Pre Tax Profit (USD), Assets (USD), Liabilities (USD) |
| **Type** | Business |
| **Configurable** | Yes — explicit currency assumption per source |
| **Default Enabled** | No |
| **Dependencies** | CLN-044 |

**Purpose:** Make currency an explicit, attached fact rather than an
assumption buried in a column name — the reference dataset's USD-ness is
only implied by its column headers, not stated as data.

**Rule Description:** Attaches a configured currency code as a derived
attribute alongside each financial field. Never infers currency from
magnitude or column name text — requires an explicit profile-level assumption.

**Input Example:** `Sales (USD) = 160319900` with `currency = "USD"` configured → **Output Example:** derived attribute `sales_currency = "USD"`.

**Potential Risks:** If enabled with a wrong configured assumption, tags
every value with an incorrect currency, silently — this is why it defaults off.

**Test Cases:**
- Given the rule enabled with `currency = "USD"` configured, expect the derived tag on every populated financial field.
- Given the rule disabled, expect no derived tag produced.

---

#### CLN-046 — Unit Scale Normalization

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Sales (USD), Assets (USD), Liabilities (USD) |
| **Type** | Business |
| **Configurable** | Yes — requires explicit source-scale metadata |
| **Default Enabled** | No |
| **Dependencies** | CLN-044, CLN-045 |

**Purpose:** Handle a future source that reports financial figures in
thousands or millions rather than raw units.

**Rule Description:** Multiplies by a configured scale factor, applied only
when the profile explicitly states the source's scale — **never inferred
from the magnitude of the numbers themselves**, since guessing "this number
looks like it's in thousands" is exactly the kind of silent assumption this
project has already been burned by once.

**Input Example (source explicitly configured as "thousands"):** `160320` → **Output Example:** `160320000`

**Potential Risks:** A wrong or missing scale configuration produces
numbers wrong by orders of magnitude — the single highest-consequence
misconfiguration risk in this registry. Disabled by default; enabling it
without explicit scale configuration should raise
`InvalidCleaningConfigurationError`.

**Test Cases:**
- Given the rule enabled with `scale = "thousands"` configured, expect a factor-of-1000 multiplication.
- Given the rule enabled with no scale configured, expect a configuration error at profile-load time, not a guess.

---

#### CLN-047 — Precision Rounding

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Sales (USD), Pre Tax Profit (USD), Assets (USD), Liabilities (USD) |
| **Type** | Business |
| **Configurable** | Yes — rounding precision |
| **Default Enabled** | No — recommended to stay off; precision loss on financial data is a significant decision, not routine cleaning |
| **Dependencies** | CLN-044 |

**Purpose:** Available for organizations with a specific display/reporting
need for rounded figures — explicitly not recommended as routine practice.

**Rule Description:** Rounds to a configured precision (e.g., nearest
thousand). Writes to a derived attribute, never overwrites the original
precise value.

**Input Example:** `160319900` rounded to nearest thousand → **Output Example:** derived attribute `sales_rounded = 160320000`; original value unchanged.

**Potential Risks:** Precision loss on financial data used for any kind of
scoring or filtering downstream could produce misleading results; kept
off by default and always additive rather than destructive for this reason.

**Test Cases:**
- Given the rule enabled with thousand-precision, expect the derived rounded value while the original remains exact.
- Given the rule disabled, expect no derived attribute.

---

#### CLN-048 — Implausible Negative Value Warning

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Sales (USD), Assets (USD), Employees (Total) — **explicitly not** Pre Tax Profit (USD) or Liabilities (USD) |
| **Type** | Warning |
| **Configurable** | Yes — the exact field list is itself configurable |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-044 |

**Purpose:** Flag implausible negative values **on a per-field basis**,
because a blanket "negative = suspicious" rule across all financial fields
would be actively wrong: dataset profiling found 140 real rows with
legitimately negative `Pre Tax Profit (USD)` (companies reporting a genuine
loss) — a case this rule must never flag.

**Rule Description:** Raises a warning if a value in the configured field
list is negative. `Pre Tax Profit (USD)` is deliberately excluded from the
default field list because negative values there are a normal, expected
business reality, not a data-quality signal.

**Input Example:** `Sales (USD) = -500000` → Warning `IMPLAUSIBLE_NEGATIVE_VALUE`. **Non-example (must NOT warn):** `Pre Tax Profit (USD) = -8379000000` (a real, legitimate value observed in profiling).

**Potential Risks:** The single biggest risk in this rule is scope creep —
someone later adding `Pre Tax Profit (USD)` back into the field list without
recalling why it was excluded. This document's Rule Description is the
permanent record of that decision.

**Test Cases:**
- Given `Sales (USD) = -500000`, expect the warning.
- Given `Pre Tax Profit (USD) = -8379000000`, expect **no** warning.
- Given `Employees (Total) = -1`, expect the warning.

---

#### CLN-049 — Employees Single-Site Exceeds Total Warning

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Employees (Single Site), Employees (Total) |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-044 |

**Purpose:** Internal cross-field consistency check — single-site
employment can never legitimately exceed total employment.

**Rule Description:** Raises a warning if `Employees (Single Site)` is
greater than `Employees (Total)`, when both are populated.

**Input Example:** `Employees (Single Site) = 5000`, `Employees (Total) = 800` → Warning `SINGLE_SITE_EXCEEDS_TOTAL_EMPLOYEES`.

**Potential Risks:** None — this is a hard logical inconsistency whenever
it occurs, not a judgment call.

**Test Cases:**
- Given Single Site > Total, expect the warning.
- Given Single Site ≤ Total, expect no warning.
- Given either field absent, expect no warning (nothing to compare).

---

#### CLN-050 — Financial Field Populated Without Sales Warning

| | |
|---|---|
| **Category** | Financial |
| **Field(s)** | Sales (USD), Assets (USD), Pre Tax Profit (USD), Liabilities (USD) |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-044 |

**Purpose:** `Sales (USD)` was the one 0%-missing revenue field in the
reference dataset; its absence alongside other populated financial fields
is an unusual, worth-noting combination — informational only.

**Rule Description:** Raises a warning if any of `Assets (USD)`,
`Pre Tax Profit (USD)`, or `Liabilities (USD)` is populated while
`Sales (USD)` is absent.

**Input Example:** `Assets (USD) = 500000`, `Sales (USD) = None` → Warning `FINANCIAL_DATA_WITHOUT_SALES`.

**Potential Risks:** None — purely informational; must not be interpreted
as a data-quality failure given `Sales (USD)`'s completeness was an
artifact of this particular dataset's export filters, not a guaranteed property.

**Test Cases:**
- Given `Assets (USD)` populated and `Sales (USD)` absent, expect the warning.
- Given both populated, expect no warning.

---

### 9.6 Industry

*Fields: `D&B Hoovers Industry`, and the six code/description pairs: `US 8-Digit SIC`, `US SIC 1987`, `NAICS 2022`, `UK SIC 2007`, `ISIC Rev 4`, `NACE Rev 2`, `ANZSIC 2006`*

#### CLN-051 — Trim & Normalize Whitespace (Industry Text Fields)

| | |
|---|---|
| **Category** | Industry |
| **Field(s)** | D&B Hoovers Industry, and all six classification *description* fields |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Baseline text hygiene for descriptive industry text fields.

**Rule Description:** Trims/collapses whitespace, Unicode NFC normalization, strips control characters.

**Input Example:** `" Food Manufacturing "` → **Output Example:** `"Food Manufacturing"`

**Potential Risks:** None.

**Test Cases:**
- Given `" Retail Trade  "`, expect `"Retail Trade"`.

---

#### CLN-052 — Classification Code Whitespace-Only Trim

| | |
|---|---|
| **Category** | Industry |
| **Field(s)** | US 8-Digit SIC Code, US SIC 1987 Code, NAICS 2022 Code, UK SIC 2007 Code, ISIC Rev 4 Code, NACE Rev 2 Code, ANZSIC 2006 Code |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Same rationale as CLN-025 (D-U-N-S) — classification codes are
identifiers, not free text, and deserve the same strict "internal characters
never touched" guarantee, including any leading zeros a given coding scheme may use.

**Rule Description:** Trims only leading/trailing whitespace on each code
field. Never reformats, re-types, or alters internal characters.

**Input Example:** `" 311111 "` → **Output Example:** `"311111"`

**Potential Risks:** None, provided this rule stays separate from any
general-purpose text-cleaning rule (same reasoning as CLN-025).

**Test Cases:**
- Given `" 2047 "`, expect `"2047"`.
- Given a code with meaningful leading zeros in some future coding scheme, expect them preserved.

---

#### CLN-053 — Code/Description Pairing Consistency Warning

| | |
|---|---|
| **Category** | Industry |
| **Field(s)** | Each of the six code/description field pairs |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-051, CLN-052 |

**Purpose:** Each classification scheme's code and description should be
populated together; one without the other suggests a partial data-entry or export issue.

**Rule Description:** Raises a warning for each pair where exactly one of
the two (code, description) is populated and the other is absent.

**Input Example:** `NAICS 2022 Code = "311111"`, `NAICS 2022 Description = None` → Warning `CODE_DESCRIPTION_PAIR_INCOMPLETE`.

**Potential Risks:** None — purely observational, checked independently per
scheme (a gap in one scheme, e.g. ISIC, doesn't imply anything about another, e.g. NAICS).

**Test Cases:**
- Given a code with no matching description, expect the warning for that pair only.
- Given both populated, expect no warning for that pair.
- Given both absent, expect no warning (nothing to be inconsistent about).

---

#### CLN-054 — Unrecognized Classification Code Warning

| | |
|---|---|
| **Category** | Industry |
| **Field(s)** | Each of the six classification code fields |
| **Type** | Warning |
| **Configurable** | Yes — reference table is versioned, bundled static data |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-052 |

**Purpose:** Flag a code that doesn't appear in the platform's own bundled
reference table for that scheme — a **structural check against static,
versioned reference data shipped with the platform**, explicitly distinct
from calling a live external system (which would be verification, out of scope).

**Rule Description:** Looks up each populated code against its scheme's
bundled reference table; raises a warning if not found.

**Input Example:** A NAICS code not present in the bundled NAICS 2022
reference table → Warning `UNRECOGNIZED_CLASSIFICATION_CODE`.

**Potential Risks:** Reference tables need periodic updates as
classification schemes revise (e.g., NAICS revises every five years);
a stale bundled table produces false-positive warnings after a scheme update
— mitigated by treating the reference table itself as versioned data (§5)
requiring its own periodic review, not a one-time import.

**Test Cases:**
- Given a code present in the bundled table, expect no warning.
- Given a code absent from the bundled table, expect the warning.
- Given the reference table updated to a newer scheme revision, expect previously-unrecognized codes to be re-evaluated correctly.

---

#### CLN-055 — Industry Description Missing While Code Present Warning

| | |
|---|---|
| **Category** | Industry |
| **Field(s)** | D&B Hoovers Industry |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-051 |

**Purpose:** `D&B Hoovers Industry` had 0% missing in the reference
dataset; its absence alongside otherwise-populated classification data is
worth surfacing.

**Rule Description:** Raises a warning if `D&B Hoovers Industry` is absent
while at least one of the six classification code fields is populated.

**Input Example:** `NAICS 2022 Code = "311111"`, `D&B Hoovers Industry = None` → Warning `INDUSTRY_LABEL_MISSING`.

**Potential Risks:** None — informational only.

**Test Cases:**
- Given a populated classification code and an absent `D&B Hoovers Industry`, expect the warning.
- Given `D&B Hoovers Industry` populated, expect no warning.

---

### 9.7 Metadata

*Fields: `Source`, `TPS Flag`, `Direct Marketing Status`, `URL`, `Email usage restriction`, `Direct phone usage restriction`, `Dedup ID`, plus `RawRecord`'s own `row_number`/`sheet_name`*

#### CLN-056 — Trim Whitespace (Metadata Text Fields)

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | Source, Direct Marketing Status, URL, Email usage restriction, Direct phone usage restriction |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Baseline text hygiene.

**Rule Description:** Trims/collapses whitespace, Unicode NFC normalization.

**Input Example:** `" D&B "` → **Output Example:** `"D&B"`

**Potential Risks:** None.

**Test Cases:**
- Given `" D&B  "`, expect `"D&B"`.

---

#### CLN-057 — URL Scheme Normalization

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | URL |
| **Type** | Business |
| **Configurable** | Yes |
| **Default Enabled** | No — prepending a scheme is a guess |
| **Dependencies** | CLN-056 |

**Purpose:** Optionally make bare-domain URLs consistently usable as links.

**Rule Description:** Prepends `https://` to a value that looks like a
bare domain (no scheme present), when enabled.

**Input Example:** `"acmecorp.com"` → **Output Example:** `"https://acmecorp.com"`

**Potential Risks:** Assumes `https://` is correct, which may not be true
for every domain (some may only serve `http://`); this is a guess, hence off by default.

**Test Cases:**
- Given `"acmecorp.com"` with the rule enabled, expect `"https://acmecorp.com"`.
- Given `"https://acmecorp.com"` (scheme present), expect no change.
- Given the rule disabled, expect no change.

---

#### CLN-058 — Boolean Flag Representation Normalization (TPS Flag)

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | TPS Flag |
| **Type** | Business |
| **Configurable** | Yes — source representation mapping |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** Same rationale as CLN-028, applied to this field.

**Rule Description:** Maps configured source string representations to
native boolean values.

**Input Example:** `"N"` (future non-Excel source) → **Output Example:** `False`

**Potential Risks:** Same as CLN-028 — an unmapped representation must
raise a signal, not silently guess.

**Test Cases:**
- Given a native boolean, expect no change.
- Given `"N"` mapped to `False`, expect `False`.

---

#### CLN-059 — Provenance Field Passthrough (row_number, sheet_name)

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | row_number, sheet_name |
| **Type** | Safe (Lossless) |
| **Configurable** | No |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** These two fields are the record's own audit trail back to the
source file — this rule exists explicitly to document that they are **never
cleaned**, so no future engineer accidentally "improves" them.

**Rule Description:** A formal no-op. `row_number` and `sheet_name` are
copied from the `RawRecord` into the `CleanedLeadRecord` unmodified, with no
transformation of any kind. This entry exists in the registry so the
guarantee is documented and testable, not merely assumed.

**Input Example:** `row_number = 42`, `sheet_name = "Results"` → **Output Example:** identical, unchanged.

**Potential Risks:** None by design — the risk this rule guards against is
someone else's rule accidentally touching these fields, not this rule's own behavior.

**Test Cases:**
- Given any `row_number`/`sheet_name` pair, expect them identical, byte-for-byte, in the output.

---

#### CLN-060 — Missing Source Warning

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | Source |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-056 |

**Purpose:** A provenance gap worth surfacing.

**Rule Description:** Raises a warning if `Source` is absent.

**Input Example:** `Source = None` → Warning `MISSING_SOURCE`.

**Potential Risks:** None.

**Test Cases:**
- Given `Source = None`, expect the warning.
- Given it populated, expect no warning.

---

#### CLN-061 — Malformed URL Shape Warning

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | URL |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-056, CLN-057 |

**Purpose:** Flag a value that looks like neither a scheme-prefixed URL nor
a bare domain — a shape check, not a reachability claim.

**Rule Description:** Raises a warning if the value doesn't match a
recognizable URL or bare-domain pattern.

**Input Example:** `"not a url"` → Warning `MALFORMED_URL_SHAPE`.

**Potential Risks:** Deliberately conservative pattern to avoid
false-positiving on unusual-but-valid domains.

**Test Cases:**
- Given `"https://acmecorp.com"`, expect no warning.
- Given `"acmecorp.com"`, expect no warning (valid bare domain).
- Given `"not a url"`, expect the warning.

---

#### CLN-062 — Dedup ID Reliability Disclaimer Warning

| | |
|---|---|
| **Category** | Metadata |
| **Field(s)** | Dedup ID |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | None |

**Purpose:** A direct, permanent carry-forward of a finding from Import
Engine dataset profiling: despite its name, `Dedup ID` was found to **not**
behave as a reliable per-contact unique key — unrelated companies were
observed sharing the same small `Dedup ID` value. This rule exists so that
fact is attached to the data itself, not just remembered informally by
whoever happened to read the original profiling report.

**Rule Description:** When `Dedup ID` is populated, attaches a standing,
low-severity informational warning restating that this field must not be
treated as a stable uniqueness key by any downstream consumer, including a
future deduplication engine.

**Input Example:** `Dedup ID = 6` → Warning `DEDUP_ID_NOT_RELIABLE` (informational, fixed message).

**Potential Risks:** Fires on nearly every record with this field
populated, which may prove noisy in practice. **Noted as a candidate for
demotion to a single dataset-level annotation (via `SourceMetadata` /
run-level stats) rather than a per-record warning**, if production usage
shows the per-record version adds noise without added value — flagged here
for a future document revision, not resolved today.

**Test Cases:**
- Given `Dedup ID` populated, expect the warning present.
- Given `Dedup ID` absent, expect no warning (CLN-034's sibling in Company handles `Key ID`'s absence; this rule only concerns the reliability disclaimer, not presence/absence).

---

### 9.8 Cross-Field Rules

Rules in this section span **two or more of the categories above**. A rule
relating multiple fields *within* a single category is documented under
that category instead (e.g., CLN-010, Contact Level vs. Title, is entirely
within Identity).

#### CLN-063 — No Contact Method Available Warning

| | |
|---|---|
| **Category** | Cross-Field (Contact) |
| **Field(s)** | Email, Direct Phone, Phone |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-018, CLN-021 |

**Purpose:** A record with no contact method at all is unusable for
outreach regardless of how complete its other fields are — worth a distinct,
higher-visibility signal beyond the individual per-field missing-value warnings.

**Rule Description:** Raises a warning if `Email`, `Direct Phone`, and
`Phone` are all absent simultaneously.

**Input Example:** All three fields `None` → Warning `NO_CONTACT_METHOD_AVAILABLE`.

**Potential Risks:** None — purely observational, and intentionally
distinct from (not a replacement for) CLN-018/CLN-021's individual field-level warnings.

**Test Cases:**
- Given all three fields absent, expect the warning.
- Given any one field populated, expect no warning from this rule (individual field warnings may still apply from CLN-018/CLN-021 as appropriate).

---

#### CLN-064 — Person Name Duplicates Company Name Warning

| | |
|---|---|
| **Category** | Cross-Field (Identity + Company) |
| **Field(s)** | First Name, Last Name, Company Name |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-001, CLN-024 |

**Purpose:** Catch a plausible column-misalignment error spanning two categories.

**Rule Description:** Raises a warning if the concatenation of
`First Name` + `Last Name` matches `Company Name` (case-insensitive).

**Input Example:** `First Name = "Acme"`, `Last Name = "Corp"`, `Company Name = "Acme Corp"` → Warning `NAME_DUPLICATES_COMPANY_NAME`.

**Potential Risks:** Low false-positive risk for legitimately
eponymous sole-proprietorships (e.g., "Jane Smith Consulting" where the
person's actual name partially matches); kept informational only.

**Test Cases:**
- Given a name matching the company name, expect the warning.
- Given distinct values, expect no warning.

---

#### CLN-065 — Address Duplicates Company Name Warning

| | |
|---|---|
| **Category** | Cross-Field (Address + Company) |
| **Field(s)** | Address Line 1, Company Name |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-024, CLN-035 |

**Purpose:** Catch a plausible column-misalignment error, complementing
CLN-043 (which checks Address Line 1 against City, staying within the
Address category) with a check against Company Name across categories.

**Rule Description:** Raises a warning if `Address Line 1` equals
`Company Name` (case-insensitive) after normalization.

**Input Example:** `Address Line 1 = "Adobe Inc."`, `Company Name = "Adobe Inc."` → Warning `ADDRESS_DUPLICATES_COMPANY_NAME`.

**Potential Risks:** None beyond the shared low false-positive risk profile of pattern-matching warnings generally.

**Test Cases:**
- Given identical values, expect the warning.
- Given distinct values, expect no warning.

---

#### CLN-066 — Email Domain Does Not Match Company Domain Warning

| | |
|---|---|
| **Category** | Cross-Field (Contact + Company + Metadata) |
| **Field(s)** | Email, URL |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-013, CLN-057 |

**Purpose:** A personal-looking email address (e.g., a Gmail domain) for a
corporate contact behaves differently in outreach than a corporate address
— a useful plausibility signal, not a truth claim about the contact.

**Rule Description:** Compares the domain portion of `Email` against the
domain portion of `URL` (after scheme normalization); raises a warning if
they don't match and `Email`'s domain isn't itself a well-known generic
provider already expected to differ (e.g., "gmail.com" is expected to
differ and is excluded from triggering this comparison as a false-positive
source unless explicitly configured otherwise).

**Input Example:** `Email = "cristinaf@justfoodfordogs.com"`, `URL = "https://acmecorp.com"` → Warning `EMAIL_DOMAIN_COMPANY_DOMAIN_MISMATCH`.

**Potential Risks:** Legitimate mismatches are common (multi-brand
companies, agencies managing outreach on a client's behalf); must remain
low-confidence and purely informational, never used to reject a record.

**Test Cases:**
- Given matching domains, expect no warning.
- Given mismatched domains where neither is a known generic provider, expect the warning.
- Given `Email` domain is a known generic provider (e.g., "gmail.com") with the default exclusion configured, expect no warning.

---

#### CLN-067 — Country-Aware Phone Default-Region Formatting

| | |
|---|---|
| **Category** | Cross-Field (Address + Contact) |
| **Field(s)** | Country/Region (read), Direct Phone / Phone (read + write) |
| **Type** | Business |
| **Configurable** | Yes |
| **Default Enabled** | No — inherits CLN-016's off-by-default status and its underlying risk |
| **Dependencies** | **Must run after CLN-038** (Country Standardization) so the record's own normalized country is available, and is a variant of CLN-016 that uses this per-record country instead of one global default region |

**Purpose:** Improve on CLN-016's single global default-region assumption
by using the record's own (already-normalized) country when formatting its
phone number — a concrete example of the cross-field rule-ordering
dependency flagged in the approved architecture discussion.

**Rule Description:** When enabled (as an alternative to, not in addition
to, CLN-016), formats `Direct Phone`/`Phone` to E.164 using the record's own
`Country/Region` field as the default region, falling back to a
profile-configured default only when `Country/Region` itself is absent.

**Input Example:** `Country/Region = "United States"` (post-CLN-038), `Phone = "1-949-722-3647"` → **Output Example:** `"+19497223647"`

**Potential Risks:** Depends entirely on `Country/Region` having already
been reliably normalized (CLN-038) — if that rule is disabled or its
reference table has gaps, this rule's region inference degrades to its
fallback default, with the same risk profile as CLN-016. This dependency
must be enforced by the pipeline's stage/rule ordering, not left to chance.

**Test Cases:**
- Given `Country/Region = "United States"` and a US-formatted number, expect correct E.164 output.
- Given `Country/Region` absent, expect the profile-configured fallback default region used instead.
- Given this rule and CLN-016 both enabled simultaneously, expect a configuration error at profile-load time (they are mutually exclusive alternatives, not additive).

---

#### CLN-068 — Financial Data Present Without Industry Classification Warning

| | |
|---|---|
| **Category** | Cross-Field (Financial + Industry) |
| **Field(s)** | Sales (USD), D&B Hoovers Industry, all six classification code fields |
| **Type** | Warning |
| **Configurable** | Yes |
| **Default Enabled** | Yes |
| **Dependencies** | CLN-044, CLN-051 |

**Purpose:** A company with real financial data but no industry
classification at all is an unusual combination worth surfacing —
complements CLN-055 (which checks the reverse direction within Industry alone).

**Rule Description:** Raises a warning if `Sales (USD)` is populated while
`D&B Hoovers Industry` and all six classification code fields are simultaneously absent.

**Input Example:** `Sales (USD) = 160319900`, every industry/classification field `None` → Warning `FINANCIAL_DATA_WITHOUT_INDUSTRY_CLASSIFICATION`.

**Potential Risks:** None — informational only.

**Test Cases:**
- Given `Sales (USD)` populated and every industry field absent, expect the warning.
- Given at least one industry field populated, expect no warning.

---

## 10. Rule ID Index

| Rule ID | Name | Category | Type |
|---|---|---|---|
| CLN-001 | Trim & Normalize Whitespace (Identity Fields) | Identity | Safe |
| CLN-002 | Name Casing Standardization | Identity | Business |
| CLN-003 | Name Suffix Normalization | Identity | Business |
| CLN-004 | Title Acronym Casing Correction | Identity | Business |
| CLN-005 | Title Abbreviation Expansion/Contraction | Identity | Business |
| CLN-006 | Missing Name Warning | Identity | Warning |
| CLN-007 | Identical First/Last Name Warning | Identity | Warning |
| CLN-008 | Name Contains Unexpected Characters Warning | Identity | Warning |
| CLN-009 | Title Unusually Long Warning | Identity | Warning |
| CLN-010 | Contact Level / Title Inconsistency Warning | Identity | Warning |
| CLN-011 | Trim & Normalize Whitespace (Email Fields) | Contact | Safe |
| CLN-012 | Strip Phone Force-Text Artifact | Contact | Safe |
| CLN-013 | Email Domain Lowercasing | Contact | Safe |
| CLN-014 | Email Local-Part Lowercasing | Contact | Business |
| CLN-015 | Primary Email Selection | Contact | Business |
| CLN-016 | Phone Number Canonical Formatting (E.164) | Contact | Business |
| CLN-017 | Primary Phone Selection | Contact | Business |
| CLN-018 | Missing Email Warning | Contact | Warning |
| CLN-019 | Malformed Email Shape Warning | Contact | Warning |
| CLN-020 | Role-Based Email Pattern Warning | Contact | Warning |
| CLN-021 | Missing Phone Warning | Contact | Warning |
| CLN-022 | Implausible Phone Digit Count Warning | Contact | Warning |
| CLN-023 | Phone Contains Non-Numeric Characters Warning | Contact | Warning |
| CLN-024 | Trim & Normalize Whitespace (Company Text Fields) | Company | Safe |
| CLN-025 | D-U-N-S Number Whitespace-Only Trim | Company | Safe |
| CLN-026 | Legal Suffix Standardization | Company | Business |
| CLN-027 | Company Name Casing Standardization | Company | Business |
| CLN-028 | Boolean Flag Representation Normalization (Is Headquarters) | Company | Business |
| CLN-029 | Missing Company Name Warning | Company | Warning |
| CLN-030 | Company Name Equals Parent Company Warning | Company | Warning |
| CLN-031 | Ticker Present Without Public Ownership Warning | Company | Warning |
| CLN-032 | Business Description Suspiciously Short Warning | Company | Warning |
| CLN-033 | D-U-N-S Number Shape Warning | Company | Warning |
| CLN-034 | Key ID Missing Warning | Company | Warning |
| CLN-035 | Trim & Normalize Whitespace (Address Fields) | Address | Safe |
| CLN-036 | Normalize Empty Address Line Representation | Address | Safe |
| CLN-037 | State/Province Standardization | Address | Business |
| CLN-038 | Country Standardization (ISO 3166) | Address | Business |
| CLN-039 | Postal Code Formatting Policy | Address | Business |
| CLN-040 | Street Abbreviation Standardization | Address | Business |
| CLN-041 | Incomplete Address Component Warning | Address | Warning |
| CLN-042 | Postal Code Shape Warning | Address | Warning |
| CLN-043 | Address Line Duplicate Content Warning | Address | Warning |
| CLN-044 | Normalize Missing-Value Representation (Financial Fields) | Financial | Safe |
| CLN-045 | Currency Unit Tagging | Financial | Business |
| CLN-046 | Unit Scale Normalization | Financial | Business |
| CLN-047 | Precision Rounding | Financial | Business |
| CLN-048 | Implausible Negative Value Warning | Financial | Warning |
| CLN-049 | Employees Single-Site Exceeds Total Warning | Financial | Warning |
| CLN-050 | Financial Field Populated Without Sales Warning | Financial | Warning |
| CLN-051 | Trim & Normalize Whitespace (Industry Text Fields) | Industry | Safe |
| CLN-052 | Classification Code Whitespace-Only Trim | Industry | Safe |
| CLN-053 | Code/Description Pairing Consistency Warning | Industry | Warning |
| CLN-054 | Unrecognized Classification Code Warning | Industry | Warning |
| CLN-055 | Industry Description Missing While Code Present Warning | Industry | Warning |
| CLN-056 | Trim Whitespace (Metadata Text Fields) | Metadata | Safe |
| CLN-057 | URL Scheme Normalization | Metadata | Business |
| CLN-058 | Boolean Flag Representation Normalization (TPS Flag) | Metadata | Business |
| CLN-059 | Provenance Field Passthrough (row_number, sheet_name) | Metadata | Safe |
| CLN-060 | Missing Source Warning | Metadata | Warning |
| CLN-061 | Malformed URL Shape Warning | Metadata | Warning |
| CLN-062 | Dedup ID Reliability Disclaimer Warning | Metadata | Warning |
| CLN-063 | No Contact Method Available Warning | Cross-Field | Warning |
| CLN-064 | Person Name Duplicates Company Name Warning | Cross-Field | Warning |
| CLN-065 | Address Duplicates Company Name Warning | Cross-Field | Warning |
| CLN-066 | Email Domain Does Not Match Company Domain Warning | Cross-Field | Warning |
| CLN-067 | Country-Aware Phone Default-Region Formatting | Cross-Field | Business |
| CLN-068 | Financial Data Present Without Industry Classification Warning | Cross-Field | Warning |

**Totals:** 68 rules — 13 Safe, 21 Business, 34 Warning.
