# Infrastructure Layer

## What "infrastructure" means here
This is where we talk to the **outside world**: databases, third-party
APIs, file formats, email servers. Anything that involves a network call, a
file on disk, or a specific vendor's SDK belongs here.

## The rule for this folder
Infrastructure code **implements** the `ports/` (interfaces) defined in
`application/ports/`. For example, `application/ports/` might one day
declare `class EmailVerifierPort(Protocol): def verify(self, email: str) ->
bool: ...`, and a file in
`infrastructure/external_services/email_verification/` would provide a
concrete class like `ZeroBounceEmailVerifier` that fulfills that contract
using ZeroBounce's real API.

**Why bother with this split?** Vendors change. Today's email-verification
company might raise prices or shut down tomorrow. Because every use case in
`application/` only ever talks to the abstract port — never to
`ZeroBounceEmailVerifier` directly — swapping vendors means writing one new
class here and changing one line of configuration. No use case, and
nothing in `domain/`, ever needs to change.

## Sub-folders

| Folder | Purpose |
|---|---|
| `database/` | Database setup: the SQLAlchemy connection/engine, session management, and (later) concrete repository classes that implement the `domain/repositories/` interfaces. |
| `excel/` | Code that reads and writes Excel files (`.xlsx`) — the technical detail of *how* a spreadsheet becomes Python data, used by the future "import Excel files" use case. |
| `external_services/email_verification/` | Talks to whichever email-verification vendor is chosen (e.g. ZeroBounce, NeverBounce, Hunter.io). |
| `external_services/phone_verification/` | Talks to whichever phone-verification vendor is chosen (e.g. Twilio Lookup, Numverify). |
| `external_services/linkedin/` | Talks to whichever LinkedIn/profile-data provider is chosen (e.g. Proxycurl). |
| `external_services/company_data/` | Talks to whichever company-info/funding-data provider is chosen (e.g. Clearbit, Crunchbase). |
| `external_services/ai_providers/` | Wraps the Anthropic (Claude) SDK calls used for generating personalized outreach messages. |
| `external_services/email_sending/` | Wraps SMTP / a transactional-email provider for actually sending the reviewed outreach emails. |

## Current status
Empty on purpose — no vendor integrations exist yet. These folders exist so
each future integration has one obvious, isolated home, and so that no
external SDK ever needs to be imported from `domain/` or `application/`.
