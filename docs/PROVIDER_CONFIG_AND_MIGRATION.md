# Merchant checkout database migration and provider settings (v0.4)

STATUS: engineering staging only, not a live banking or lending operation.

## Sensitive configuration
The submitted SSLCOMMERZ store password, database passwords and earlier Render API credential were disclosed in chat. Assume they are compromised and rotate all of them with the issuing providers. Do not reuse them in production. This repository does not store those values.

The submitted callback URLs mixed two distinct domains. Do not copy them. Instead configure SLICKK_PUBLIC_BASE_URL to ONE controlled and TLS-verified HTTPS origin. The app generates all four paths on that same host: /v1/gateway/return/success, /return/fail, /return/cancel and /v1/gateway/ipn. Verify DNS control, TLS certificates and merchant-panel IPN registration.

The submitted DB hosts and claimed regulatory/store approvals have not been independently verified. Use the real provider-supplied private DB hostname, verified CA and read-only login instead of hard-coded example values. An authorization claim or a payment store ID alone does not establish a licence or settlement agreement.

## One authoritative checkout record
The existing merchant_checkouts table remains the source of truth. Migration 001_merchant_checkout_audit.sql creates timezone-aware created/updated timestamps, status indexes, a state-event audit table, and an internal reconciliation view. Legacy created timestamps remain NULL when unknown. Events can be altered by DB administrators, so production requires access restrictions, immutable backups and independent oversight.

We intentionally do NOT store payment card PAN/card_no, customer name, email or phone, or provider passwords in merchant checkout records. The gateway's card_no field must not be copied from IPN or validation responses. A gateway-verified payment ('paid') is NOT proof of bank settlement.

## Operator-only database procedure
1. Rotate and securely store credentials. Keep SLICKK_ENABLE_CHECKOUTS=false, SLICKK_GATEWAY_LIVE=false, SLICKK_REGULATORY_SIGNOFF=false.
2. Make a backup and obtain database change approval. With a migration-capable PostgreSQL account and TLS, apply: psql -v ON_ERROR_STOP=1 -f migrations/001_merchant_checkout_audit.sql
3. Explicitly provision a read-only reporting user with SELECT on merchant_checkout_reconciliation only. Do not grant PUBLIC access or write permissions.
4. Keep DATABASE_READ_URL in a private secret store with sslmode=verify-full and correct CA/hostname. Run on an approved workstation: python scripts/export_reconciliation.py --day 2026-11-03 --output reconciliation-2026-11-03.csv
5. This export is an INTERNAL reconciliation report, NOT the mandatory Bangladesh Bank filing format. Reconcile provider payment records with actual bank settlements and outstanding refunds/chargebacks.
6. Confirm merchant legal entity, live account scope, licensed partner arrangement, settlement account, production domain, penetration test, monitoring and refund handling before any real payment. Wallet issuance, credit disbursement and remittances require separate reviewed authorization and are blocked from this merchant checkout route.

Official gateway guide: https://developer.sslcommerz.com/doc/v4/
