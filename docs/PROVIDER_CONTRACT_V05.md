# Slickk Pay v0.5 — Gateway contract and safe integration

**Status: NOT LIVE. This is a merchant-only checkout adapter.** It does not issue e-money, wallet balances, loans, international remittances or bank deposits.

## Confidential configuration and approvals
Previous SSLCOMMERZ, PostgreSQL and hosting credentials disclosed in the conversation must be considered exposed and rotated with their respective providers. Do not reuse them or place replacements in GitHub, tickets, chat, CI, example files or request URLs. The supplied initiation SUCCESS and validation VALID JSON are unverified examples, not independent proof of real money received or a real merchant account. A provider-issued store ID does not by itself prove a Bangladesh Bank authorization or the permitted product scope. Independently verify legal entity, payment gateway onboarding, settlement account, and written partner/regulatory permissions.

Use private hosting secrets and only these environment **names**:
- SSLCOMMERZ_STORE_ID — newly issued merchant store identifier.
- SSLCOMMERZ_STORE_PASSWD — newly issued merchant password. Legacy SSLCOMMERZ_STORE_PASSWORD is supported; conflicting values fail startup.
- SSLCOMMERZ_IS_SANDBOX — optional boolean, must not contradict SLICKK_GATEWAY_LIVE. Declaring false alone cannot activate production.
- SLICKK_GATEWAY_LIVE — explicit production routing flag, disabled by default.
- SLICKK_ENABLE_CHECKOUTS, SLICKK_REGULATORY_SIGNOFF — remain false until reviewed evidence and approved launch.
- SLICKK_PUBLIC_BASE_URL — one verified HTTPS origin; SLICKK_CALLBACK_PREFIX=/v1/payments creates /v1/payments/success, /fail, /cancel and /ipn under the same origin. Legacy /v1/gateway paths remain functional.
- DATABASE_URL — private TLS PostgreSQL connection for the existing checkout records. DATABASE_READ_URL — optional SELECT-only reporting account. Validate CA, hostname, role privileges and replication lag.

The merchant gateway initiation and validation hosts are fixed in app.live, not dynamically overridden by user-supplied URLs; this protects merchant credentials from endpoint spoofing. Verify DNS/TLS for the intended callback host before registering it with the gateway.

## Trusted processing
Create a unique checkout reference for a nonregulated merchant sale, request a gateway session and validate the returned gateway redirect host. A gateway session SUCCESS response only means **checkout created**, not paid. The success/fail/cancel browser redirects never change financial state. Only a provider-verified IPN can record 'paid' after matching val_id, tran_id, BDT currency and gross amount with the existing order and examining risk signals and bank reference. A reported store_amount must be positive and not exceed gross; it is **not confirmation of bank settlement**. Finance must reconcile with gateway and settlement-bank statements. Never credit a wallet or disburse a loan from this callback.

## Why the proposed SQL is not executed
Continue using merchant_checkouts as the single checkout record, plus merchant_checkout_state_events and merchant_checkout_reconciliation from migration 001. Do not introduce a competing transactions table with separately mutable statuses. Do not persist card_no, raw IPN payload/validation JSON, customer IP, phone, email or names, or raw credentials in checkout/audit tables. The existing reconciliation view is an internal report, not a certified Bangladesh Bank regulatory format. Merchant management, disputes, refunds, settlement accounting, lending and wallet issuance require distinct scoped reviews.

## Release gates
Run python -m unittest discover -s tests -v (mock provider only), rotate leaked credentials, validate independent regulatory/partner authorization, private PostgreSQL backup and role boundaries, IPN registration and allowlists, CA verification, security review, gateway sandbox end-to-end, chargeback/refund support, reconciliation with bank statements, operational monitoring and incident response. Render staging must use app.live:app and start with checkout flags OFF. No live transaction or production database migration was attempted in this integration.

Official developer reference: https://developer.sslcommerz.com/doc/v4/
