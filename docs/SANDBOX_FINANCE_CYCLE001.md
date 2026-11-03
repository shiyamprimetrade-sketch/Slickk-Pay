# Cycle 001 — independent fictitious-money banking research core

**Environment:** offline sandbox, always fictional money. **Not an account that stores real customer value, licensed lender, bank, PSP, live cash agent, or live payment gateway.** This package is original Slickk Pay code, separate from SSLCOMMERZ merchant checkout (`app.live`) and from the earlier demo wallet (`app.main`).

## What is implemented

- `pricing.py`: exact BDT decimal parsing, versioned pilot assumptions for free customer transfers and cash-in, BDT 10.99/1,000 cash-out, BDT 5.50/1,000 cash-out commission, BDT 1.50/1,000 cash-in commission, and a 0.45% test merchant fee. These are hypotheses, not approved tariffs or profitability results.
- `identity.py`: synthetic mobile numbers, customer/agent roles, masked lookup, frozen status, and synthetic agent locations. Does **not** perform real KYC, SMS verification, device binding or PIN handling.
- `ledger.py`: persistent SQLite, balanced immutable event postings, hash-linked journal, idempotency, single-process serialized writers, insufficient-balance protection, reconstructed balances and reconciliation checks. `synthetic_issuer` may carry a negative balance solely to reflect fictional test issuance. No bank account or payment network is connected.
- `workflows.py`: customer-to-customer fictitious transfers; agent cash-in after separate synthetic customer token; cash-out reservation, simulated cash handover and commission; cancellation and traceable audit events. Physical cash declarations are fictional operator inputs.
- `api.py`: explicit locally enabled sandbox-only API, separate from hosted checkout. It must not be deployed to Render as a financial-service API.

## Known limitations and safety gates

- Within a single SQLite file, each simulated cash reservation, confirmation and cancellation now commits its journal and cash-state mutations in one SQL transaction. A failed statement rolls back both. This has **not** been benchmarked for multi-process/high-availability production use. Production still requires PostgreSQL concurrency controls, staged deployment, outbox-driven recovery, and independent financial review.
- No real consumer authentication, ID verification, financial identity, PCI compliance, remote gateway connectivity, licensed agent enrollment, bank settlement or AML monitoring exists here.
- The local simulator returns a synthetic customer confirmation token as part of its test API response; this is expressly not a valid real customer authorization channel.
- Shadow ledger operations in `app.ops` are non-settling, independent from this fictional balance engine. They are not general-ledger records of a licensed financial entity.
- No source file in this cycle should be used to process actual money. No incoming IPN may credit this sandbox automatically.
- Fees and commissions are pilot assumptions. The pricing module exposes contribution margin before real service costs and identifies simulations.

## Local reproduction

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q app
```

For local API tests without real network exposure, use FastAPI `TestClient` and `build_sandbox_app`. Optional development command (only after setting a 32+ character locally generated secret):

```bash
export SLICKK_SANDBOX_LOCAL_ONLY=true
export SLICKK_ENV=staging
export SLICKK_ENABLE_CHECKOUTS=false
export SLICKK_SANDBOX_CONTROL_KEY="<locally-generated-random-key>"
uvicorn 'app.sandboxfinance.api:local_only_app' --factory --host 127.0.0.1 --port 8091
```

Do not set production flags or expose port 8091 publicly. The real checkout application remains `app.live:app` and untouched by the sandbox route factory.

## Important follow-up engineering

1. Consolidate cash request + ledger event + physical inventory state into one atomic PostgreSQL transaction with unique idempotency identifiers, retries and recovery journal.
2. Implement independent account PIN/MFA and agent verification, identity proofs, fraud and dispute controls, with secure account lifecycle and audit.
3. Add account opening and transfer velocity ceilings as policy models, sanctions/risk simulations, more concurrency tests and regional cashflow stress cases.
4. Develop Android-first UI over authenticated, simulated endpoints; no offline financial finalization.
5. Document evidence for licensed PSP/banking arrangements separately before any real-money integration.

## Extended simulated domains

- `gateway.py`: independent internal sandbox merchant enrolment, invoice/payment intent, synthetic customer consent, capture, cancellation, full refund, and immutable audit events. This is **not** a real card or MFS processing gateway. `slickkpay-sandbox://` URIs cannot be presented as actual merchant QR acceptance codes.
- `loans.py`: synthetic loan-size/term experiments, explainable affordability policy, flat decreasing-balance interest schedule, manual decision, treasury-funded synthetic disbursement, exact repayments, and overdue reporting. None of these records is a real borrower, credit bureau finding, financial product disclosure or lending authorization.
- `limits.py`: persistent velocity reservations, rolling-hour/daily ceilings, distinctive counterparty count and review thresholds. Callers must include reservations and ledger postings in the **same transaction**; the module alone does not make a payment safe or compliant.
- `agency.py`: approval-controlled fictional float replenishment and cash-demand forecasts; source of float must be the fictional treasury, with no physical-float transfer claim.
- `security.py`: synthetic-only passphrase hashing, local device labels represented as digests, session scopes, revocation and lockouts. It is a research model, not a production identity service; no real user secrets should enter its fixtures.
- `support.py`: case lifecycle, reviewer assignment, hashed evidence references and immutable action log; cannot trigger financial reversal or operational refund.
- `receipts.py`: English/Bangla receipts, signing of local copies and verification against the fictitious journal. Outputs explicitly warn that no money moved.
- `reports.py`: synthetic active account and transaction breakdowns, invariant findings, privacy-minimized aggregate CSV and cash-flow scenario modeling.
- `scenarios.py`: deterministic cross-module acceptance using fictional customers, agents, merchant and operator, including balanced journal assertions.

## Operational review gates

1. Every new source module is intentionally disconnected from real payment gateway, bank settlement, telecom identity checks, and external transfers.
2. The internal merchant gateway only moves already issued **fictional** balances inside the local ledger. No real Visa, Mastercard, SSLCOMMERZ, NPSB, Binimoy or MFS connectivity is implemented by these modules.
3. Every transition is test-scoped. The sandbox administrator/control key is not customer identity authentication and must not be reused in production.
4. Customer cash-in/out confirmation tokens are returned only to a synthetic caller during tests; production requires a separated, authenticated customer approval channel and double-confirmed agent cash handover.
5. The sample platform net-margin calculator omits multiple real cost types and does not prove profitability or permitted tariffs.
6. The sandbox credit cost illustrations are not loan offers, lender records or consumer creditworthiness assessments.
7. Before any real financial service, independently verify legal authorization, audit infrastructure, formal security threat model, KYC/AML obligations, bank settlement processes, and appropriate regulated partners.
