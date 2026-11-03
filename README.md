# Slickk Pay & Credit — Sandbox v0.1

**STATUS: SOFTWARE RESEARCH PROTOTYPE, NOT A BANK OR LICENSED FINANCIAL SERVICE.**

A local, responsive Bangladesh-focused fintech exploration app with fictional BDT funds. Nothing connects to banks, bKash, Nagad, international remittance networks, payment gateways, or Bangladesh Bank. No real lending or money movement occurs.

## Run on Windows 11 (PowerShell)

1. Install Python 3.11+ from python.org if necessary.
2. Unzip the project, open PowerShell in its main folder.
3. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** on the same computer. This is deliberately accessible only locally.

On Mac/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On Mac/Linux replace the python path with `.venv/bin/python`.

## Features implemented

- Mobile-responsive dashboard with two fictional demo customers and fictional merchants.
- Demo wallet balances derived from immutable journal entries, integer poisha amounts, SQLite transactions, double-entry bookkeeping.
- P2P transfers and merchant payments (fictional balances only).
- Idempotent operation IDs; duplicate retries don't create additional transfers.
- Simulated direct-to-biller e-Payment Credit quote/disbursement/repayment using **maximum-fee lookup** from Bangladesh Bank BRPD-1 Circular No. 17 dated September 6, 2026.
- Credit is never deposited to borrower wallet; eligible example billers are utilities and education.
- One open demo loan per customer, full repayment, fee display, ledger integrity audit.
- No real identities, mobile numbers, NID, biometric or bank card data.

## Known limitations — blockers to production

- **No authentication, sessions, MFA, access control, abuse prevention, rate limits or CSRF protection.** Anyone with local access to this demo can operate any sample profile and reset state. DO NOT expose it to a public network.
- No live payments, disbursement, remittances, wallet custody or external API integrations.
- No real bank or lender authorization, bank-partner agreement, PSP/PSO approval, MFS licence, foreign-exchange licence, or legal opinion.
- No consent record, actual e-KYC, AML/CFT screening, sanctions checks, anti-fraud engine, credit bureau checks, credit underwriting, affordability assessment, data residency review, customer support, disclosures, collections, complaints or audit retention policy.
- The credit fee table is an illustrative maximum fee schedule, **not a product quote approved by a lender**. Penalties, arrears, taxes, accounting recognition, settlement and applicable classification/reporting rules are not implemented.
- SQLite and this minimal ledger are demonstrators, not an audited or fault-tolerant production core banking system.
- `POST /api/demo/reset` deliberately wipes all sandbox activity and resets demo balances. No production deployment allowed.

## Architecture to build next (after licensed partnership)

Client app (Android/web) -> authenticated BFF/API -> risk & compliance checks -> payment orchestration -> bank/MFS/PSP partner APIs -> reconciliation and immutable accounting store -> monitoring and regulatory reporting.

Credit: user consent and KYC -> regulated bank credit policy / eligibility / CIB -> lender-approved offer with full disclosure -> direct eligible biller payment -> contractual repayment through bank partner -> disputes and collections with proper controls.

Remittance: authorised remittance provider -> local licensed payout bank/MFS partner, subject to FX and regulator requirements. No independent cross-border transfer in current release.

## Official references reviewed (November 2, 2026)

- Bangladesh Bank Guidelines to Establish Digital Bank, Version 2 (Aug 20, 2025): https://www.bb.org.bd/aboutus/regulationguideline/brpd/digitalbank_version-2_english.pdf
- Bangladesh MFS Regulations 2022: https://www.bb.org.bd/aboutus/regulationguideline/psd/mfs_regulations_2022.pdf
- Bangladesh Bank BRPD-1 Circular No 17, e-Payment Credit (Sep 6, 2026): https://www.bb.org.bd/mediaroom/circulars/brpd/sep062026brpd-117e.pdf
- Bangladesh Bank revised e-KYC circular (March 11, 2026, effective Sep 1, 2026): https://www.bb.org.bd/mediaroom/circulars/brpd/mar112026brpd-108e.pdf
- MRA regulatory overview: https://www.bb.org.bd/en/index.php/financialsystems/regulator
- BB PSD framework and provider list: https://www.bb.org.bd/en/index.php/financialsystems/paysystems

Regulatory applicability must be validated with qualified Bangladeshi legal/regulatory counsel before any live service or public brand usage implying banking authorization.

---

## v0.2 — Separate gateway-backed checkout service (integration candidate)

**Do not publicly run the old `app.main:app` sandbox.** A new separate ASGI application, `app.live:app`, has been added for a licensed merchant's **SSLCOMMERZ hosted checkout** integration. Its checkout endpoints are OFF by default, and it has no demo-wallet transfers, fake loans, reset endpoint, remittances, or custodied funds. The new service requires a high-entropy server-side merchant API key and always validates provider IPNs against the gateway validation API before marking an order paid. No actual gateway transaction has been attempted.

- Deployment and approval checklist: [docs/LIVE_GATEWAY_AND_DEPLOYMENT.md](docs/LIVE_GATEWAY_AND_DEPLOYMENT.md)
- Example non-secret configuration: [.env.example](.env.example)
- Docker entrypoint: `app.live:app`, **not** the local `app.main:app`.
- Tests: `python -m unittest discover -s tests -v`.

**Deployment is not the same as regulatory approval or a live transaction.** Live checkout is blocked until the actual licensed entity/merchant agreement, provider credentials, persistent PostgreSQL, HTTPS and operational reviews have been supplied and verified. User financial data and real loans require separate safeguards and authorization. Never paste API keys, NID scans or private authorisation documents into public GitHub.

## v0.3 — Render staging blueprint (not yet deployed)

The Render Blueprint [`render.yaml`](render.yaml) defines **disabled-by-default staging only** with a free staging PostgreSQL instance. See [`docs/RENDER_STAGING_DEPLOYMENT.md`](docs/RENDER_STAGING_DEPLOYMENT.md) for deployment steps, key rotation instructions, and go/no-go checks. The app accepts Render's default `postgresql://` database URL using the `psycopg` SQLAlchemy dialect. The local-only demo is **never** selected by the deployment Dockerfile. Run `python -m unittest discover -s tests -v` before promoting a build. No provider contracts, approvals, or real transactions are established by running this software.

## v0.4 — Gateway configuration and data migration

- Merchant-only checkout now blocks regulated wallet top-ups, loans and remittances.
- Added PostgreSQL state audit / reconciliation migration, and a read-only UTC-day report export.
- No provided secrets are committed, and no live payment was initiated.
- See docs/PROVIDER_CONFIG_AND_MIGRATION.md before any deployment.
