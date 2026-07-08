# Application Layer

## What "application" means here
This layer holds the **use cases** — the specific things a user or the
system can *do*: "import an Excel file", "verify a lead's email", "generate
an outreach message", "send an approved email". Each use case is a
step-by-step recipe that orchestrates the domain layer to accomplish one
clear goal.

Think of the **domain** layer as the dictionary of business concepts, and
the **application** layer as the sentences written using that dictionary.

## The rule for this folder
Code here is allowed to depend on `domain/`, but must **never** depend on
`infrastructure/` or `interfaces/` directly. Instead of calling, say,
SQLAlchemy or the Anthropic SDK directly, a use case depends on a `port`
(an abstract interface defined in `ports/`). The real implementation is
"plugged in" later from `infrastructure/`. This pattern is called
**Dependency Inversion** — it's the same idea as a lamp with a standard
plug: the lamp (use case) doesn't care which power company (infrastructure)
is behind the socket, as long as the plug shape (port) matches.

## Sub-folders

| Folder | Purpose |
|---|---|
| `use_cases/` | One file per user-facing action. **Implemented:** `import_dataset.py` (`ImportDatasetUseCase`), `clean_dataset.py` (`CleanDatasetUseCase`), `resolve_identity.py` (`ResolveIdentityUseCase`), `enrich_subject.py` (`EnrichSubjectUseCase`), `compare_executive.py` (`CompareExecutiveUseCase`), `detect_inflections.py` (`DetectInflectionsUseCase`), `verify_contact.py` (`VerifyContactUseCase`), `process_executive.py` (`ProcessExecutiveUseCase` — runs the full Executive Processing Pipeline). Still to come: `generate_outreach_message.py`, etc. Each use case reads like a short story: "get the lead, check it, call the verifier, save the result." |
| `services/` | Shared logic used by *multiple* use cases that doesn't belong to one specific business entity (e.g. a scoring/ranking helper). Keeps use cases from duplicating logic. |
| `ports/` | Abstract interfaces ("contracts") that describe what the application layer *needs* from the outside world. **Implemented:** `source_reader_port.py` (`SourceReaderPort`), `cleaning_rule_port.py` (`NormalizationRule`, `QualityCheckRule`), `identity_candidate_port.py` (`IdentityCandidatePort` — no concrete implementation yet; tests use an in-memory fake), `enrichment_provider_port.py` (`EnrichmentProviderPort` — implemented by `infrastructure/enrichment/company_website/`), `verification_provider_port.py` (`VerificationProviderPort`, `EmailVerificationPort`, `PhoneVerificationPort` — no concrete implementations yet; tests use an in-memory fake). Still to come: `AIMessageGeneratorPort`, `EmailSenderPort`. Infrastructure code implements these interfaces — this is what makes "replace a vendor" a one-file change instead of a rewrite. |
| `dto/` | **D**ata **T**ransfer **O**bjects — simple data shapes used to move information into and out of use cases. **Implemented:** `models.py` (Import Engine: `RawRecord`, `SourceMetadata`, `ImportWarning`, `ImportedLeadDataset`), `cleaning_models.py` (Cleaning Engine: `FieldChange`, `QualityWarning`, `CleanedLeadRecord`, `CleaningMetrics`, `CleaningReport`, `CleaningResult`), `identity_resolution_models.py` (Identity Resolution Engine: `IdentitySignal`, `ExtractedIdentity`, `IdentityRecord`, `ConfidenceScore`, `MatchCandidate`, `IdentityAuditEntry`, `ReviewQueueItem`, `IdentityResolutionResult`), `enrichment_models.py` (Enrichment Provider Framework: `EnrichmentRequest`, `EnrichmentResponse`, `ObservationCandidate`, `ProviderPriority`, `ProviderHealth`, `ProviderSkip`, `EnrichmentCoordinationResult`), `comparison_models.py` (Executive Comparison Engine: `ComparisonStatus`, `ComparisonStrategy`, `FieldComparison`, `ComparisonSummary`, `ComparisonResult`), `inflection_models.py` (Inflection Detection Engine: `InflectionType`, `Inflection`, `InflectionReport`), `verification_models.py` (Contact Verification Framework: `ContactType`, `VerificationStatus`, `VerificationRequest`, `VerificationResult`, `VerificationProviderSkip`, `VerificationCoordinationMetrics`, `VerificationReport`), `executive_pipeline_models.py` (Executive Processing Pipeline: `ExecutiveProcessingStatus`, `ExecutiveProcessingReport`), `evaluation_models.py` (Evaluation & Validation module: `ExecutiveEvaluationRow`, `EvaluationSummary`, `EvaluationRun`) — kept separate from domain entities so the domain doesn't have to know about them. |
| `cleaning/` | The Cleaning Engine — a cohesive sub-package (68 rules, `CLN-001`–`CLN-068`), not a flat layer folder, since it's pure in-memory rule logic with no I/O. See `cleaning/README.md`. |
| `identity_resolution/` | The Identity Resolution Engine (Version 1) — signal extraction, candidate generation, confidence scoring, and auto-merge/review/new-identity decisions, per the approved Identity Resolution RFC. Pure in-memory logic, no I/O. See `identity_resolution/README.md`. |
| `enrichment/` | The Enrichment Provider Framework (Version 1) — provider registry, priority ordering, refresh policy, health tracking, and coordination across multiple external sources. Its first concrete provider, Company Website, is implemented in `infrastructure/enrichment/company_website/`. See `enrichment/README.md`. |
| `comparison/` | The Executive Comparison Engine (Version 1) — compares an existing executive record against newly collected `ObservationCandidate`s, field by field, and reports differences (never their meaning). Pure in-memory logic, no I/O. See `comparison/README.md`. |
| `inflection/` | The Inflection Detection Engine (Version 1) — converts a `ComparisonResult` into deterministic, explainable business events (Promotion, Demotion, Company Change, Possible Resignation, Contact Information Changed, Executive Newly/No-Longer-Found). Pure in-memory logic, no I/O. See `inflection/README.md`. |
| `verification/` | The Contact Verification Framework (Version 1) — provider coordination, priority ordering, and per-provider configuration for verifying email addresses and phone numbers before outreach. No concrete provider (NeverBounce, ZeroBounce, Kickbox, Bouncer, Twilio Lookup, Numverify, Abstract API) is implemented yet. Pure in-memory logic, no I/O. See `verification/README.md`. |
| `executive_pipeline/` | The Executive Processing Pipeline (Version 1) — wires the Enrichment Provider Framework, Executive Comparison Engine, Inflection Detection Engine, and (if configured) Contact Verification Framework together to process one executive end to end. No new provider, no framework redesign — pure orchestration. See `executive_pipeline/README.md`. |
| `evaluation/` | The Evaluation & Validation module (Version 1) — a `PipelineRunner` that runs every executive in an Excel file through the existing Executive Processing Pipeline and produces a CSV report plus summary metrics measuring how well the platform performs. No new provider, no AI, no automation, no redesign — pure measurement. See `evaluation/README.md`. |

## Current status
The Import Engine's, Cleaning Engine's, Identity Resolution Engine's,
Enrichment Provider Framework's, Executive Comparison Engine's,
Inflection Detection Engine's, Contact Verification Framework's,
Executive Processing Pipeline's, and Evaluation & Validation module's use
cases, ports, and DTOs are implemented — see
`infrastructure/importers/README.md`, `cleaning/README.md`,
`identity_resolution/README.md`, `enrichment/README.md`,
`comparison/README.md`, `inflection/README.md`, `verification/README.md`,
`executive_pipeline/README.md`, and `evaluation/README.md` for the full
picture. `services/` remains empty on purpose; no other use cases exist
yet.
