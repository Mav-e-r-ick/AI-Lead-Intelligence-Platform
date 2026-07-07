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
| `use_cases/` | One file per user-facing action. **Implemented:** `import_dataset.py` (`ImportDatasetUseCase`), `clean_dataset.py` (`CleanDatasetUseCase`), `resolve_identity.py` (`ResolveIdentityUseCase`). Still to come: `verify_lead_contact_info.py`, `generate_outreach_message.py`, etc. Each use case reads like a short story: "get the lead, check it, call the verifier, save the result." |
| `services/` | Shared logic used by *multiple* use cases that doesn't belong to one specific business entity (e.g. a scoring/ranking helper). Keeps use cases from duplicating logic. |
| `ports/` | Abstract interfaces ("contracts") that describe what the application layer *needs* from the outside world. **Implemented:** `source_reader_port.py` (`SourceReaderPort`), `cleaning_rule_port.py` (`NormalizationRule`, `QualityCheckRule`), `identity_candidate_port.py` (`IdentityCandidatePort` — no concrete implementation yet; tests use an in-memory fake). Still to come: `EmailVerifierPort`, `AIMessageGeneratorPort`, `EmailSenderPort`. Infrastructure code implements these interfaces — this is what makes "replace a vendor" a one-file change instead of a rewrite. |
| `dto/` | **D**ata **T**ransfer **O**bjects — simple data shapes used to move information into and out of use cases. **Implemented:** `models.py` (Import Engine: `RawRecord`, `SourceMetadata`, `ImportWarning`, `ImportedLeadDataset`), `cleaning_models.py` (Cleaning Engine: `FieldChange`, `QualityWarning`, `CleanedLeadRecord`, `CleaningMetrics`, `CleaningReport`, `CleaningResult`), `identity_resolution_models.py` (Identity Resolution Engine: `IdentitySignal`, `ExtractedIdentity`, `IdentityRecord`, `ConfidenceScore`, `MatchCandidate`, `IdentityAuditEntry`, `ReviewQueueItem`, `IdentityResolutionResult`) — kept separate from domain entities so the domain doesn't have to know about them. |
| `cleaning/` | The Cleaning Engine — a cohesive sub-package (68 rules, `CLN-001`–`CLN-068`), not a flat layer folder, since it's pure in-memory rule logic with no I/O. See `cleaning/README.md`. |
| `identity_resolution/` | The Identity Resolution Engine (Version 1) — signal extraction, candidate generation, confidence scoring, and auto-merge/review/new-identity decisions, per the approved Identity Resolution RFC. Pure in-memory logic, no I/O. See `identity_resolution/README.md`. |

## Current status
The Import Engine's, Cleaning Engine's, and Identity Resolution Engine's
use cases, ports, and DTOs are implemented — see
`infrastructure/importers/README.md`, `cleaning/README.md`, and
`identity_resolution/README.md` for the full picture. `services/` remains
empty on purpose; no other use cases exist yet.
