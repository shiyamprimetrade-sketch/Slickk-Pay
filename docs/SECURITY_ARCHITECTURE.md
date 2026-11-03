# Security architecture — sandbox evidence

## Controls implemented

- Explicit environment guard blocks remote PostgreSQL targets and production/live mode.
- All value is fictional. Immutable posted journal and posting rows are protected by PostgreSQL triggers; SQLite unit tests use equivalent test triggers.
- Owner checks block synthetic cross-account transfers. Limits and a row-locked journal head prevent overspending and conflicting velocity checks.
- Customer and agent roles are distinct in cash workflow; the agent cannot confirm a customer's synthetic token in the service method.
- Cash-out after customer confirmation is conservatively disputed on ambiguous expiration. Electronic escrow is not silently released.
- Synthetic HMAC grants support bounded lifetime, key versioning, device-digest check and durable consumed nonce records.
- Outbox leases use a random token, bounded retries, payload allowlists, no PII, and unique event/destination keys.
- Security findings are hash-linked and store digest of synthetic subject ID rather than raw profile data.
- Diagnostic redaction removes sensitive keys, credentials, mobile numbers and email patterns.
- Read-only API does not expose money-moving routes, and returns no-store headers.

## Not proven or not implemented

No real consumer authentication, KYC, MFA, device trust, PIN, secure enclave, liveness detection, penetration test, malware screening, AML monitoring, legal authorization or regulator signoff has been verified. The HMAC keyring is only a **synthetic test mechanism**; it is not an authorization system for actual customer funds. The hash chain lacks independently controlled immutable notarization. A real bank transfer would need extensive additional safeguards and approved licensed networks.

Never put SSLCOMMERZ, Render, database or customer credentials in the repository, CI logs, app bundles or chat. Previously disclosed credentials require rotation at their issuers before any connection.
