# Cycle 003 — Slickk Pay Android-first mobile sandbox

**Status:** original React Native/TypeScript prototype code, not a production payment application. The authoritative service remains the isolated, disabled-by-default `app.live:app` merchant checkout, plus separately opt-in fictional ledgers (`app/sandboxfinance` and `app/pgsandbox`). No mobile route can post a balance, release agent cash, settle an invoice, issue credit, or access an actual financial network.

## Architectural decision

**Decision:** introduce an Android-first React Native/Expo prototype in `apps/mobile-sandbox`, while retaining Python financial cores and the TypeScript read-only inspection SDK. SDK 57 is used to align with React Native 0.86 and React 19.2.3; Expo's own documentation indicates that SDK 58 is newer but SDK 57 remains relevant for Expo Go compatibility during transition. Keep this app separate from `app.live:app`, and do not ship privileged operator inspection credentials to end users.

**Rationale:** the existing API offers private operator inspection, not end-user consent/authorization. A client built directly on its operator key would constitute a dangerous privilege transfer. Local fictional fixtures provide a safe starting point for accessible mobile UX without inventing a customer payment API.

**Known infrastructure boundary:** no new deployed service, PostgreSQL schema, settlement route, payment integration or Redis cluster is introduced in this cycle. The mobile app remains an independent package that does not alter existing merchant checkout or production databases.

## Implemented mobile domains

1. Strict integer BDT/poisha handling and proposed-fee display, including precision/overflow guards and pilot rates explicitly labeled as hypotheses.
2. Synthetic persona and account isolation for customer, agent and merchant views; no KYC or real identity verification.
3. Draft-only transfer, merchant and cash quote creation with explicit review acknowledgment and terminal cancellation/expiration states.
4. Agent directory, liquidity shortfall warnings, sample commissions and unverified physical-handover tabletop states.
5. Sample transaction activity, receipts, merchant invoices and support/dispute drafts, never proof of actual bank settlement.
6. Bilingual copy, readable financial labels, privacy masking, notification previews and accessible UI primitives.
7. Strongly fail-closed mobile read contracts, session limits, redacted local logs, offline recovery and prohibition on queuing financial actions.
8. Synthetic QR scheme and duplicate-field rejection; no real MFS or bank QR interoperability.
9. Traceable app state and view models with explicit `simulation:true`, `serverState:not_sent`, `canMoveMoney:false` and no production credential storage.

## Security review findings

- An agent must not impersonate a customer or confirm a handover from a single local screen. The tabletop UI is limited to quotes/checklists; actual two-party authentication requires a future server-backed workflow.
- No operator API key, SSLCOMMERZ password, database URL or customer secret is embedded in the mobile project.
- Backend authentication, transaction status reconciliation, device Keystore verification, customer KYC, risk approvals, Android build/runtime testing and network authorization remain incomplete. No live money features are enabled.
- Customer-facing prices are pilot assumptions: cash-out fee ৳10.99 per ৳1,000; cash-in free; customer transfer free; agent cash-in commission ৳1.50 per ৳1,000; agent cash-out commission ৳5.50 per ৳1,000; merchant fee 0.45%, with taxes unverified. Never treat these as approved tariffs.

## Verification and next gates

- Standalone mobile core: `cd apps/mobile-sandbox && npm run test:core`.
- React Native typecheck (after npm installation): `npx tsc --noEmit -p tsconfig.json`.
- GitHub Actions workflow: `.github/workflows/mobile-cycle003.yml` tests mobile TypeScript, strict React Native TSX, and Android JavaScript export. Check actual hosted result before describing it as verified.
- Existing Python and PostgreSQL CI must remain green on this branch; no branch merge to main is authorized.

**Next gate:** peer review of native UX and security, a real Android emulator/device build, privacy/accessibility walkthrough, and contract for an authenticated, server-authoritative customer/agent sandbox API before any network-based financial operations.
