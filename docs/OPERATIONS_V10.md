# Slickk Pay v1.0 — Merchant operations research and staging previews

**Status:** Non-settling, staging-only operations tooling. Not a bank, regulated wallet, settlement processor, or license certification. No third-party provider account was accessed. Every feature added here is independent original implementation.

## Purpose

Build a dependable operational foundation for merchant payment investigation without inventing evidence of completed money movement. The source-of-truth provider, bank, and merchant must each retain authority for their respective records. A program's local consistency is **not equivalent** to a regulator, merchant acquirer, or bank certifying a transaction.

The previously implemented hosted checkout lives in `app/live.py`. The fictional wallet simulator remains in `app/main.py` and is excluded from the Docker deployment. This upgrade introduces independent tools under `app/ops/` and optional staging-only endpoints. It does not alter SSLCOMMERZ initiation or transaction-validation logic.

## Added modules

| Module | Capability | Limit |
| --- | --- | --- |
| `primitives.py` | exact BDT minor units, typed evidence, canonical hashes, redaction | cannot verify source authenticity |
| `catalog.py` | merchant-authoritative SKU pricing, tax, expiry, policy, quote fingerprint, invoice-idempotency | in-memory reference catalog, no production billing |
| `journal.py` | balanced evidence postings, reversals and SHA-256 hash chain | shadow audit only, no customer funds |
| `settlement.py` | gateway vs bank batch matching, fee checks, duplicates, risk states and strict CSV | bank evidence is operator-supplied and must be externally confirmed |
| `risk.py` | deterministic merchant-only policy, provider risk hold, velocity assessment | advisory, no automated approval, no KYC/AML engine |
| `disputes.py` | case state machine, evidence digests, timestamps, reviewer attribution | no refund, representment, chargeback or gateway action |
| `security.py` | HMAC notification signatures, key rotation and nonce replay tests, HTTPS host allowlisting | does not verify provider callbacks; no network transport |
| `outbox.py` | idempotent notification staging, leases and bounded retries | network sending deliberately not implemented |
| `reports.py` | aggregate metadata snapshot and documentary gate checklist | no regulatory filing, no independent evidence review |
| `api.py` | protected stateless staging reconciliation/risk/readiness previews | off by default; no persistence or provider calls |

### Trust boundaries

1. **Merchant catalog:** Merchant's authoritative backend, not browser-supplied price values.
2. **Gateway:** Independent `val_id` validation and risk level from the actual payment provider.
3. **Bank:** Independent bank credit statement, not a gateway's `store_amount`.
4. **Shadow journal:** Derived analysis; should never become the source of customer stored value.
5. **Dispute desk:** Human case workflow; not an automatic reversal/refund system.
6. **Operations previews:** Caller-provided evidence is untrusted. A hypothetical report finding of `settled` is an **analytical match**, not a confirmed bank deposit unless checked against original bank statements by authorized personnel.
7. **Authorization:** A self-reported set of checklist flags is not independently verified compliance and cannot activate production. The API always responds `production_ready: false`.

## Environment variables

By default `SLICKK_OPS_PREVIEW_ENABLED=false`. It must only ever be set to `true` in an isolated staging environment with an existing private 32+ character `SLICKK_MERCHANT_API_KEY`. If enabled on a production service, startup fails. The flag is explicitly set to `false` in the checked-in Render Blueprint.

Never include credentials in Git, test fixtures, issue comments, uploaded screenshots, or chat. Previously disclosed Render, gateway and PostgreSQL credentials must be revoked and replaced in their own service dashboards.

## Staging-only preview endpoints

- `GET /v1/ops/contract`: public, factual capabilities and disabled-state information.
- `POST /v1/ops/reconcile/preview`: merchant-authenticated, max 100 gateway and 100 bank records, strict BDT values, no customer information.
- `POST /v1/ops/risk/preview`: merchant-authenticated deterministic advisory assessment. No persistence.
- `POST /v1/ops/readiness/preview`: merchant-authenticated documentary gate checks. All claims are operator-supplied and unverified; never a production go-ahead.

Every private endpoint requires `X-Slickk-Api-Key`. Any missing key is denied. All request bodies forbid unknown fields. The endpoints are available only with the explicit preview flag; they can be tested with FastAPI's in-process `TestClient` without any HTTP exposure.

### Example: local, isolated preview

Use the existing checkout service only, not the fictional wallet service.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:SLICKK_ENV="staging"
$env:SLICKK_ENABLE_CHECKOUTS="false"
$env:SLICKK_GATEWAY_LIVE="false"
$env:SLICKK_OPS_PREVIEW_ENABLED="false"
.\.venv\Scripts\python.exe -m uvicorn app.live:app --host 127.0.0.1 --port 8000
```

To inspect nonfinancial capabilities only, open `http://127.0.0.1:8000/v1/ops/contract`. For protected preview testing, use the in-process tests rather than enabling an internet-facing endpoint. Do not switch flags on a production host.

## Reconciliation rules

- Amount inputs are fixed-point BDT strings at the API boundary and integer poisha internally. Floats, exponent notation, missing currency, and rounding ambiguity are rejected.
- A gateway record must have `gross = gateway_net + provider_fee`; it must have original independent validation and zero risk to be eligible for match.
- Batch references are explicit. No fuzzy matching on customer name, partial phone number, or card details.
- A bank credit with duplicate statement reference, unverified documentation, mismatched amount, a timestamp before gateway payment, or no corresponding gateway batch will never be counted as unqualified settlement.
- Missing bank evidence is distinguished between the assumed settlement window and a record overdue relative to that window. Actual T+1/T+2 scheduling must come from a merchant's written agreement, not a software assumption.
- The reconciliation preview always emits `real_bank_settlement_confirmed: false` even when typed records agree. A bank reconciliation officer must independently check statements and audit trails.
- CSV importer accepts an exact minimal schema. Any additional customer PII, card or unrecognized columns cause the input to be rejected.

## Risk handling

The risk evaluator consumes only merchant IDs, references, BDT amounts, provider validation/risk, merchant invoice checks, and precomputed aggregate counts. It never requests PAN, national ID, phone, address, biometrics, or personal purchase history. Policies are scoped to a merchant, versioned, and immutable within recorded assessments.

`allow_to_validate` is **not** a payment authorization. It means only that a candidate can proceed to the external payment-provider's independent validation gate. Any missing verification, missing provider risk classification, or provider risk above zero blocks automatic promotion.

## Disputes and refund safety

Cases can move through `open`, `triage`, `waiting_merchant`, `waiting_provider`, `evidence_complete`, `resolved/rejected`, and `closed`. Only listed transitions are supported. Resolution requires an evidence digest. Each case event contains previous/next state, reviewer reference, UTC timestamp, and a hash link to the preceding event.

No automatic refund or dispute submission is made. Real provider refund APIs require separate review, account authorization, settlement reconciliation, customer notification, and audit controls.

## Outbound notification safety

The outbox intentionally contains **no HTTP client or external delivery worker**. It models an append-only event reference, safe payload digest, per-merchant isolation, bounded lease, deterministic retry delay, and explicit endpoint allowlisting. HMAC signatures use a distinct key ID/nonce/version/purpose and validity period. Signing keys stay in private memory for local tests; actual production keys belong in a secret manager.

Do not confuse outgoing merchant notification signatures with SSLCOMMERZ IPN authentication. SSLCOMMERZ IPNs remain untrusted and require server-to-server provider validation using private credentials.

## Shadow accounting journal

The journal is intentionally separate from the existing checkout and from the fictional demo wallet. Each event requires balanced debits/credits, valid merchant-scoped accounts, stable idempotency reference, and an immutable SHA-256-linked entry. Reversals are new entries, not history rewrites. This is an **offline audit trail**, not a production regulatory ledger or source of financial balances. Database persistence, backups, access control, legal books of record and reconciliation ownership remain outside its verified scope.

## Verification

```bash
python -m compileall -q app/ops
python -m unittest discover -s tests -v
```

The suite uses in-memory data, SQLite test databases and mocked SSLCOMMERZ requests. The existing disposable PostgreSQL CI workflow continues to exercise SQL migrations 001–003; this upgrade adds no production database migration. No live gateway, Render, or bank credentials were used.

## Next milestones

1. Independent review and approval of this operations-layer API contract and access boundaries.
2. Private rotation confirmation for all previously exposed credentials; configure Render through the authorized provider account, never by pasting keys here.
3. Obtain a genuine staging HTTPS URL, signed-off isolated database migration, and private sandbox SSLCOMMERZ credentials.
4. Execute a real provider sandbox payment with safe merchant service category; document IPN delivery, validation, risk, duplicate callback and outcome.
5. Obtain independent bank settlement statements and verify a first reconciliation by a designated settlement officer.
6. Design durable, audited, access-controlled storage for reviewed operational cases (PostgreSQL migrations, optimistic concurrency, per-merchant row-level permissions). Do not deploy this in-memory layer as a production money ledger.
7. Run threat modeling, load tests, backup/restore drills, incident response, PII/privacy review, and compliance signoff before any live-money release.

**Release status:** code-only upgrade, draft PR, no production financial activation.
