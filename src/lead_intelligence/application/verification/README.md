# Contact Verification Framework

Implements Version 1 of the Contact Verification layer: a provider-
agnostic framework for confirming that an email address or phone number is
still valid before an executive is contacted, without coupling the rest of
the platform to any specific verification vendor.

## Scope: what Version 1 does and does not do

**Does:** define the one contract every verification provider must
implement (`VerificationProviderPort`), its two narrower specializations
for each contact type (`EmailVerificationPort`, `PhoneVerificationPort`),
the request/result/report shapes providers exchange with the coordinator,
per-provider configuration (enabled/priority/timeout), and a
`VerificationCoordinator` that determines which providers apply, executes
them in priority order, and combines their results.

**Does not:** implement any real provider, message sending, or AI. No
NeverBounce, ZeroBounce, Kickbox, Bouncer, Twilio Lookup, Numverify, or
Abstract API integration yet. Every concrete provider is a future task:
one new class implementing `EmailVerificationPort` or
`PhoneVerificationPort`, handed to `VerificationCoordinator`. Nothing in
this framework needs to change when that happens.

## How the pieces communicate

```
VerifyContactUseCase                    (application/use_cases/verify_contact.py)
        |
        v
VerificationCoordinator                (coordinator.py)
        |
        |-- reads --> VerificationProfile     (config.py)   "enabled? priority?"
        |-- reads --> each provider's own supported_contact_types
        |
        |-- for each applicable, enabled provider,
        |   in ascending ProviderPriority order:
        |       VerificationRequest -> provider.verify() -> VerificationResult
        |
        v
VerificationReport                      (application/dto/verification_models.py)
  = provider_results: tuple[VerificationResult, ...]
  + skipped_providers: tuple[VerificationProviderSkip, ...]
  + metrics: VerificationCoordinationMetrics
```

**Execution, per contact detail (`VerificationCoordinator.verify`):**
1. **Filter to applicable providers**: only providers whose own
   `supported_contact_types` includes the requested `ContactType` are
   considered at all (e.g. a phone-only provider is never even considered
   for an email address). These providers are structurally inapplicable,
   not "skipped" — they never appear in `skipped_providers`.
2. **Order by priority**: remaining providers are sorted by their
   `VerificationProviderConfiguration.priority` (ascending — `CRITICAL`
   first), with `provider_id` as a stable tiebreaker.
3. For each, in order, gate on one check — failing it produces a
   `VerificationProviderSkip` with `VerificationSkipReason.DISABLED` and
   the provider is never called: `VerificationProfile.is_enabled(provider_id)`.
4. Otherwise, build one `VerificationRequest` and call `provider.verify()`,
   guarded so an unexpected exception is caught, logged, and recorded as an
   `ERROR` result — one misbehaving provider never stops the others.
5. Every executed provider's `VerificationResult` is collected into the
   returned `VerificationReport`, unresolved — see below.

## Why the coordinator never picks a "winning" verdict

When two enabled providers disagree about the same contact detail (one
reports `VALID`, another `RISKY`), this framework reports both, exactly as
returned — the same restraint the Executive Comparison Engine exercises
around the differences it identifies. Deciding which provider to trust, or
how to combine multiple verdicts into one final decision, is explicitly
future work, not part of "the verification framework."

## `VerificationStatus`: verdict and technical outcome, in one enum

Mirrors `EnrichmentStatus`'s own shape: `VALID`/`INVALID`/`RISKY`/`UNKNOWN`
describe what the provider concluded about the contact detail itself,
while `ERROR`/`TIMEOUT`/`RATE_LIMITED` describe the provider *call* failing
— independent of anything about the contact detail. The coordinator's
`providers_succeeded`/`providers_failed` metrics count the latter three as
failures and everything else (including the uncertain `RISKY`/`UNKNOWN`
verdicts) as a successful provider call, since the provider did answer.

## Why `EmailVerificationPort` / `PhoneVerificationPort` exist separately
from `VerificationProviderPort`

A future NeverBounce/ZeroBounce/Kickbox/Bouncer adapter only ever verifies
email; a future Twilio Lookup/Numverify/Abstract API adapter only ever
verifies phone numbers. Fixing `supported_contact_types` in these two
narrower base classes means a concrete provider only has to implement
`provider_id`, `display_name`, and `verify()` — it can never accidentally
claim to support the wrong contact type. `VerificationCoordinator` still
only depends on the common `VerificationProviderPort`, so it works
identically regardless of which of the two a given provider is.

## Why there is no `RefreshPolicy` or `ProviderHealth` here (unlike the
Enrichment Provider Framework)

Version 1 scope for this framework is deliberately narrower than the
Enrichment Provider Framework's: refresh staleness and circuit-breaker
health tracking were not requested for contact verification, and adding
them now would be scope creep beyond "implement only the verification
framework." A future task can add either without changing
`VerificationProfile`'s public shape. Likewise, there is no separate public
registry class — `VerificationCoordinator` takes its providers directly
(dependency injection) and guards duplicate `provider_id`s inline, raising
`DuplicateVerificationProviderError`.

## Configuration (`config.py`)

- `VerificationProviderConfiguration` — `enabled`, `priority`,
  `timeout_seconds` (validated and carried for a future infrastructure
  adapter to enforce during real I/O — not enforced by this pure,
  synchronous Version 1 coordinator), and fully opaque `parameters` for
  provider-specific settings this framework never interprets.
- `VerificationProfile.default_configuration` — what a newly registered
  provider with no explicit profile entry runs under, so adding a new
  provider never requires updating every existing profile.
- `VerificationProfile.validate()` fails the whole run before any provider
  executes if the profile is self-contradictory (mirrors
  `EnrichmentProfile.validate()`).
- `ProviderPriority` is reused from `enrichment_models.py` rather than
  redefined — "lower value runs first" is not enrichment-specific, the
  same reuse precedent `SubjectType` already set.

## Adding a future concrete provider without modifying this framework

1. Write one class implementing `EmailVerificationPort` or
   `PhoneVerificationPort` (`application/ports/verification_provider_port.py`)
   — `provider_id`, `display_name`, and `verify()` — in a new
   `infrastructure/verification/<provider_name>/` module. All real I/O
   (HTTP calls, auth, rate-limit handling, vendor SDKs) lives there, never
   in this package.
2. Pass an instance into `VerificationCoordinator`.
3. Optionally add a `VerificationProviderConfiguration` entry to the active
   `VerificationProfile` for non-default priority/enabled settings.

`VerificationCoordinator` and `VerificationProfile` never change — neither
names a specific provider.

## Files

| File | Responsibility |
|---|---|
| `config.py` | `VerificationProviderConfiguration`, `VerificationProfile`, `default_profile`. |
| `coordinator.py` | `VerificationCoordinator` — provider lookup + duplicate-id guard, priority ordering, gating, fail-safe execution, aggregation. |
| `application/ports/verification_provider_port.py` | `VerificationProviderPort`, `EmailVerificationPort`, `PhoneVerificationPort`. |
| `application/dto/verification_models.py` | `ContactType`, `VerificationStatus`, `VerificationSkipReason`, `VerificationRequest`, `VerificationResult`, `VerificationProviderSkip`, `VerificationCoordinationMetrics`, `VerificationReport`. |
| `application/use_cases/verify_contact.py` | `VerifyContactUseCase` — thin orchestration entry point. |
| `domain/exceptions/verification_exceptions.py` | `LeadVerificationError`, `InvalidVerificationConfigurationError`, `DuplicateVerificationProviderError`. |

Tests: `tests/unit/verification/` — configuration validation,
`EmailVerificationPort`/`PhoneVerificationPort`'s fixed contact-type
support, and an end-to-end coordinator suite (priority ordering and
tie-breaking, disabled-provider skipping, unsupported-contact-type
providers never even being considered, fail-safe handling of a raising
provider, technical-failure vs. successful-call metrics classification,
duplicate-provider-id guarding, and determinism) plus the use case wrapper
— all against `FakeVerificationProvider`, an in-memory stand-in for the
real providers this task deliberately does not implement.
