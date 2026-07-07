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
| `use_cases/` | One file per user-facing action (e.g. `import_leads_from_excel.py`, `verify_lead_contact_info.py`, `generate_outreach_message.py`). Each use case reads like a short story: "get the lead, check it, call the verifier, save the result." |
| `services/` | Shared logic used by *multiple* use cases that doesn't belong to one specific business entity (e.g. a scoring/ranking helper). Keeps use cases from duplicating logic. |
| `ports/` | Abstract interfaces ("contracts") that describe what the application layer *needs* from the outside world — e.g. `EmailVerifierPort`, `AIMessageGeneratorPort`, `EmailSenderPort`. Infrastructure code implements these interfaces. This is what makes "replace the email-verification vendor" a one-file change instead of a rewrite. |
| `dto/` | **D**ata **T**ransfer **O**bjects — simple data shapes used to move information into and out of use cases (e.g. "the input needed to run the Excel-import use case"), kept separate from domain entities so the domain doesn't have to know about API request/response shapes. |

## Current status
Empty on purpose. No use cases have been implemented yet — this task is
foundation only.
