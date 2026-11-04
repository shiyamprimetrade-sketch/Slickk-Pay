# Slickk Pay Cycle 005 — typed customer/agent access SDK

This is a **local-only fictional-data contract SDK**, not a bank client and not a production payment gateway. The SDK communicates only with an explicitly configured loopback Cycle 004 FastAPI laboratory, which itself lacks a financial-posting route.

- Code: `clients/simaccess-sdk/src` (strict TypeScript, NodeNext, no runtime third-party dependencies).
- Run: `cd clients/simaccess-sdk && npm install --no-package-lock --ignore-scripts && npm test`.
- Python contract: `SLICKK_SIM_ACCESS_ENABLED=true python -m scripts.verify_cycle005_contract` from the repository root, with `SLICKK_ENABLE_CHECKOUTS=false`, `SLICKK_GATEWAY_LIVE=false`, `SLICKK_REGULATORY_SIGNOFF=false`.
- The SDK accepts only `http(s)://localhost`, `127.0.0.1` or `[::1]`, never a remote provider endpoint or an actual bank. **A real Android handset cannot reach a developer PC's loopback service through this SDK**; a future reviewed remote-auth model is needed before deployment.
- Device-bound demo bearers remain in memory. No `AsyncStorage`, local database, or mobile app package embeds the operator inspection key. No actual PIN or real customer identity should be used.
- POST preview mutations are never automatically retried after ambiguous failures. Server idempotency references must be inspected first. GET reads have bounded retries only when error classification allows it.
- Amounts remain integer poisha, with strict checks that server quotes balance. Taxes and price assumptions are not verified tariffs.
- Signed sample QR codes are parsed only as nonpayment previews; cryptographic verification and replay suppression remain server-side.
- Results always have explicit simulation warnings and cannot authorize cash delivery, ledger posting, bank settlement, customer deposits, or lending.
- UI projection helpers supply Bangla and English warnings and accessible status explanations; no new native APK or screen integration is claimed in this cycle.

## Verified boundaries and defects corrected

The TypeScript source checks C004's actual Python response shapes, including its `sample_*` activity statuses, support categories (`question`, `privacy`, `incorrect_quote`, `suspected_fraud`), omission of support owner ID from owner-scoped responses, and `sample_balance_poisha` representation. The SDK adds JSON content-type on POST, output-size limits, origin/redirect restrictions, and memory-only cache policy.

## Not part of the release

Real-money API access, KYC, MFA, provider onboarding, live agent cash handling, bank settlements, credit decisions, private credentials, and production payments remain unimplemented or disabled. The new SDK does not replace existing Python/Go/SQL modules or the React Native prototype, and is not wired into `app.live:app`.
