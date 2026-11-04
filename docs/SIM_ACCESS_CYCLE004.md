# Slickk Pay — Cycle 004: isolated customer/agent access simulation

## Purpose

Create a bounded, authenticated **synthetic** customer and agent lab without changing any
existing merchant checkout, bank account, PostgreSQL ledger or production environment.
The objective is reproducible security engineering, not production mobile banking.

## Implemented

- Original `app/simaccess` Python package: isolated SQLite schema, synthetic fixture-only
  identity registry, local enrolled devices, scrypt-derived test PINs, opaque server-side
  sessions, expiration and revocation, role-based access policies and fixed-window limits.
- Immutable access audit hash chain; minimal redacted event data, replay tracking,
  signed sample `slickkpaylab://` QR references and independent verification.
- Server-generated pilot fee quotes with integer poisha, stable idempotency keys,
  expiry, cancel, local review and non-financial request event histories.
- Agent cash availability checklist plus two-person review acknowledgements. **Both
  acknowledgements mean only that both personas examined the draft.** A database
  CHECK constraint permanently forbids recording a cash handover as authorized.
- Sample-only balances, activity, agent discovery, receipts, support drafts,
  risk hints, notifications, read-only analytics and bilingual fee disclosures.
- Localhost-only FastAPI API. Synthetic actors must be provisioned by an opted-in
  local fixture routine, not an anonymous public enrollment route.
- Fail-closed offline, privacy, contract version and financial-capability policies.
- Recovery worker expires *previews only*; it does not retry or queue monetary commands.

## Explicit boundaries

The application must NEVER be mounted into `app.live:app`. No live wallet, cash,
loan, settlement, bank connection, customer identity/KYC or genuine payment exists.
`app/pgsandbox` from Cycle 002 remains the separate fictional-money ledger lab;
this package does **not** import or post transactions into it.

The only supported host source IPs in the HTTP boundary are `127.0.0.1`, `::1`,
`localhost` and FastAPI TestClient's `testclient`. The lab must be bound to loopback
at the operating system/network layer as well; app middleware is **not** a
replacement for a firewall. Never forward it through a public proxy.

## Running the tests

From the repository root, with existing `requirements.txt` installed:

```bash
python -m compileall -q app/simaccess
python -m unittest discover -s tests -p 'test_simaccess_*cycle004.py' -v
python scripts/verify_cycle004_lab.py
```

Only in the local sandbox, if actually launching its server, construct a
`LabStore(..., opted_in=True)` against an explicitly named local
`sim_access_*.sqlite3` file; register **synthetic** actors and explicitly set
`SLICKK_SIM_ACCESS_ENABLED=true` before `create_local_access_app(lab,
explicitly_opted_in=True)`. No startup hook auto-creates public actors.

## API overview (local only)

`GET /lab/v4/health`, `GET /lab/v4/capabilities` and
`GET /lab/v4/contracts` advertise simulation limitations.

`POST /lab/v4/session` accepts an already-seeded synthetic identity, enrolled
fictional device and demo PIN. Authenticated routes require both `Authorization:
Bearer ...` and `X-Sim-Device` and include `/lab/v4/me`, `/lab/v4/activity`,
`/lab/v4/agents`, `/lab/v4/quotes`, `/lab/v4/requests`, sample receipts, support
drafts, QR previews and two-party cash review. All API responses carry a
simulation disclaimer. No route exists for `ledger/post`, `wallet/credit`,
`cash/confirm`, `loans/disburse` or bank settlement.

`GET /lab/v4/audit-proof` and `/lab/v4/operator/metrics` require a synthetic
operator. Real user records are not accessible through these functions.

## Financial pricing

Cash-out BDT 10.99/1000, cash-in and customer transfers free, agent cash-out
commission BDT 5.50/1000, cash-in BDT 1.50/1000, and merchant processing fee
0.45% are **unapproved pilot hypotheses**. This lab does not infer taxes or
assert final payable tariffs. Risk/commission estimates are examples only.

## Security and operational gaps

This code does not demonstrate real-phone verification, national ID checks,
biometric/Keystore enrollment, mobile app attestation, fraud clearance,
independent penetration testing, high availability or actual banking license.
Scrypt and opaque demo sessions are not a substitute for a production
identity provider or multi-factor authentication. Runbook and privacy review
are necessary before handling real customer data.

No Android APK, real device install, provider sandbox payment, bank settlement,
Render staging deploy, or financial license is established by this cycle.
Previously disclosed credentials must be privately rotated; no new secrets
are checked into GitHub or required by the local simulation.

## Release checks

CI must pass the isolated Cycle 004 unit suite and the local fault probe,
plus all inherited Cycle 001–003 application/PG/TypeScript/mobile workflows.
The stacked PR remains draft; `main` unchanged until formal review.
