# v0.8 terminal IPN safeguards (staging candidate only)

- No browser redirect or unsigned FAILED/CANCELLED IPN can mark an order paid, failed or cancelled.
- Checkout records already in failed, cancelled, refunded, or disputed states cannot be changed by the gateway callback endpoint. This does **not create** those states; refund/dispute workflows are not implemented.
- Existing paid or risk_review checkouts acknowledge an already validated repeat only if the incoming val_id matches the stored reference.
- Rejected callbacks for **known terminal checkout IDs** produce an audit row with no raw request body, payment secrets, card details, customer PII, or raw val_id. The supplied ID is represented only by SHA-256 digest.
- Audit rows are **not** a complete tamper-proof forensic logging system. Rate limiting, logging retention, access control and incident response are still needed.
- SQL migration 002 is additive and repeatable; review/backup and apply it only in a separately approved isolated staging environment. CI executes migrations only against disposable localhost PostgreSQL.
- A gateway-verified paid status does **not** prove bank settlement.

Open items: operator-only, provider-authoritative failed/cancelled transitions; refunds/chargebacks/disputes; rate limiting; independent provider and settlement reconciliation. Production payments remain disabled.
