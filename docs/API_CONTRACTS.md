# Cycle 002 read-only API contract

`app.pgsandbox.api.create_inspection_app` is an **opt-in isolated lab**, never mounted by `app.live`. It requires an explicitly supplied operator key of 48+ characters and returns `Cache-Control: no-store`. No internet-facing deployment has been authorized or performed.

All paths are prefixed `/sim/v2/` and only support GET:

| Route | Response meaning |
| --- | --- |
| `health` | Public sandbox-only health and read-only flags |
| `capabilities` | Feature flags; live bank/settlement/credit states forced false |
| `proof` | Journal hash chain and debit-credit equality evidence |
| `security-proof` | Redacted security hash-chain proof |
| `accounts/{id}` | Fictional account state, operator-only |
| `accounts/{id}/statement` | Fictional journal lines, bounded |
| `accounts/{id}/audit` | Reconstructed account posting totals |
| `reconciliation/{id}/{YYYY-MM-DD}` | Internal-only matching, never bank settlement |
| `dashboard` | Synthetic aggregate counts and states |
| `agent/{agent_float}/{commission_account}` | Synthetic cash, float, commission and activity |

The TypeScript client under `clients/inspection-sdk` uses Fetch only, validates response shapes, and rejects any response claiming non-sandbox capabilities. SDK methods have no payment operations, stored credentials or offline spending authorization. The operator key is retrieved through a callback; applications must use a secure host-managed secret facility rather than localStorage.

This API and SDK are **not** suitable to replace strong customer identity, scopes, MFA, CSP, CSRF defenses, replay protected POSTs, rate limiting or public-bank compliance systems.
