# NeverBounce Email Provider

The Contact Verification Framework's first concrete provider: verifies one
email address via [NeverBounce](https://www.neverbounce.com)'s v4 "single
check" REST API, so an executive's email can be confirmed safe to use
before outreach.

Implements `application/ports/verification_provider_port.py`'s
`EmailVerificationPort`, exactly like every future email provider
(ZeroBounce, Kickbox, Bouncer) will. Nothing in
`application/verification/` (the framework) knows this class exists — it's
wired in by whatever future orchestration layer constructs a
`VerificationCoordinator`.

## Scope: what this task does and does not do

**Does:** implement one provider adapter (NeverBounce) using the existing
`VerificationProviderPort`/`EmailVerificationPort`, read its API key from
an environment variable, map every documented NeverBounce outcome onto
this framework's fixed `VerificationStatus` vocabulary, retry transient
failures, time out slow requests, and log every step.

**Does not:** redesign the Contact Verification Framework, implement
phone verification, implement AI, or implement outreach messaging. Every
other future email provider is unaffected — none of `application/verification/`
changed to add this one.

## Environment variable

| Variable | Required | Description |
|---|---|---|
| `NEVERBOUNCE_API_KEY` | Yes | Your NeverBounce API key. Get one at https://app.neverbounce.com/settings/api. |

```bash
# .env
NEVERBOUNCE_API_KEY=your-neverbounce-api-key-here
```

```python
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.provider import (
    NeverBounceEmailProvider,
)
from lead_intelligence.infrastructure.external_services.email_verification.neverbounce.settings import (
    NeverBounceSettings,
)

provider = NeverBounceEmailProvider(settings=NeverBounceSettings.from_env())
```

`NeverBounceSettings.validate()` runs at construction time — a blank or
missing API key raises `ValueError` immediately, rather than silently
sending an unauthenticated request on the first `verify()` call.

## How the pieces communicate

```
VerifyContactUseCase                    (application/use_cases/verify_contact.py)
        |
        v
VerificationCoordinator                (application/verification/coordinator.py)
        |
        |-- for the "email" ContactType, in priority order:
        |       VerificationRequest -> NeverBounceEmailProvider.verify()
        |
        v
NeverBounceEmailProvider.verify()        (provider.py)
        |
        |-- _check(email)  ->  GET {base_url}/single/check?key=...&email=...
        |                       (retry + timeout, see below)
        |
        v
VerificationResult                      (application/dto/verification_models.py)
```

## Example request

```
GET https://api.neverbounce.com/v4/single/check?key=YOUR_API_KEY&email=ada%40example.com
```

## Example response

A deliverable address:

```json
{
  "status": "success",
  "result": "valid",
  "flags": ["has_dns", "has_dns_mx", "smtp_connectable"],
  "suggested_correction": "",
  "execution_time": 486
}
```

An undeliverable address:

```json
{
  "status": "success",
  "result": "invalid",
  "flags": ["has_dns", "has_dns_mx"],
  "suggested_correction": "",
  "execution_time": 312
}
```

A configuration/auth problem:

```json
{
  "status": "auth_failure",
  "message": "Invalid API key"
}
```

## Error mapping

`_check()` inspects both the HTTP status code and (for HTTP 200 responses)
the JSON body's own `status` field — NeverBounce reports several of its
own error conditions with HTTP 200, not an HTTP error code.

| NeverBounce outcome | Detection | `VerificationResult.status` | Retried? |
|---|---|---|---|
| Deliverable address | body `status="success"`, `result="valid"` | `VALID` | — |
| Undeliverable address | body `status="success"`, `result="invalid"` | `INVALID` | — |
| Disposable/temporary mailbox | body `status="success"`, `result="disposable"` | `RISKY` | — |
| Catch-all domain | body `status="success"`, `result="catchall"` | `RISKY` | — |
| Could not determine | body `status="success"`, `result="unknown"` | `UNKNOWN` | — |
| Rate limit (vendor-reported) | body `status="throttle_triggered"` | `RATE_LIMITED` | Yes, then `RATE_LIMITED` |
| Rate limit (HTTP-level) | HTTP 429 | `RATE_LIMITED` | Yes, then `RATE_LIMITED` |
| Temporary outage | body `status="temp_unavail"` | `ERROR` | Yes, then `ERROR` |
| Server error | HTTP 5xx | `ERROR` | Yes, then `ERROR` |
| Invalid API key | body `status="auth_failure"` | `ERROR` | No — a retry cannot fix a bad key |
| General API failure | body `status="general_failure"` | `ERROR` | No |
| Bad referrer | body `status="bad_referrer"` | `ERROR` | No |
| Malformed/non-JSON response | response body is not valid JSON | `ERROR` | No |
| Other 4xx | HTTP 4xx (not 429) | `ERROR` | No |
| Connection error | `httpx.RequestError` | `ERROR` | Yes, then `ERROR` |
| Request timeout | `httpx.TimeoutException` | `TIMEOUT` | Yes, then `TIMEOUT` |

`result="disposable"` and `result="catchall"` both map to `RISKY` — see
`provider.py`'s module docstring for why: this task must not redesign the
framework's fixed `VerificationStatus` enum, and `RISKY` already means
"deliverable/reachable but flagged as uncertain," which covers both.
NeverBounce's own, more specific classification is never lost: it's
preserved verbatim in `VerificationResult.reason` (a human-readable
sentence) and the full JSON payload in `VerificationResult.raw_response`.

## Retry and timeout (`settings.py`)

- Every request uses `settings.timeout_seconds` (default 10s) as its
  per-request timeout.
- A timeout, connection error, `5xx` response, HTTP 429, or a body-level
  `throttle_triggered`/`temp_unavail` status is retried up to
  `settings.max_retries` additional times (default 2), with linear backoff
  (`settings.retry_backoff_seconds * attempt`, default 0.5s base).
- Anything else — a bad API key, a general API failure, a bad referrer, an
  ordinary 4xx, or a non-JSON body — is never retried; retrying a
  configuration problem cannot make it succeed.

## Confidence

`VerificationResult.confidence` is always `None` for this provider.
NeverBounce's single-check endpoint reports a categorical `result`, not a
numeric probability — reporting a fabricated confidence score would be
dishonest. `VerificationResult.reason` carries the human-readable
explanation instead.

## Files

| File | Responsibility |
|---|---|
| `provider.py` | `NeverBounceEmailProvider` — the `EmailVerificationPort` implementation; retry/timeout-guarded HTTP call, result/status mapping, logging. |
| `settings.py` | `NeverBounceSettings` — API key, base URL, timeout, retries, backoff; `from_env()` reads `NEVERBOUNCE_API_KEY`. |

Tests: `tests/unit/neverbounce/` — settings validation and `from_env()`
(including real `os.environ` via `monkeypatch`), provider identity
(`provider_id`/`display_name`/`supported_contact_types`), every documented
NeverBounce `result` value's status mapping, every API-level error status
(`auth_failure`/`general_failure`/`bad_referrer`/`throttle_triggered`/
`temp_unavail`), HTTP-level failures (429/5xx/4xx/timeout/connection
error) and their retry behavior, and one integration test proving this
provider runs correctly through the real
`VerificationCoordinator` — all against `httpx.MockTransport`, never a
real network call.
