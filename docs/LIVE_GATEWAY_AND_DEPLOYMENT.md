# Slickk Pay v0.2 — merchant checkout integration and deployment gate

**Status:** Code-complete integration candidate, **not deployed**, not externally certified, no real transaction conducted.  **No direct lending, remittances, deposit-taking, customer balances or card storage.**

## 1. Isolation and architecture

- `app.main:app` = historical **local-only fictional-money** demo, includes a destructive reset API. **NEVER expose it publicly.**
- `app.live:app` = isolated merchant-hosted checkout integration. No demo-wallet, demo-credit, reset or balance endpoints are mounted. All checkouts are disabled by default.
- Merchant backend authenticates with a high-entropy `X-Slickk-Api-Key` **server-to-server**. Never put this secret in a web browser, mobile APK, JavaScript or public repository.
- Merchant backend POSTs an order reference and a BDT amount. Slickk stores one unique local transaction per order reference, calls the gateway session API and returns a gateway URL for the merchant to redirect the customer.
- SSLCOMMERZ collects the payment. Slickk must never handle the customer's card, PIN, OTP or payment-account credentials.
- SSLCOMMERZ IPN posts an event. Slickk treats it as untrusted, independently calls the **Order Validation API over TLS**, checks provider transaction ID, validation ID, amount, BDT currency, merchant store ID when provided and risk flag, then marks it `paid` or `risk_review`. Duplicate calls do not credit or fulfill twice.
- Browser redirect to `/v1/gateway/return/{success|fail|cancel}` never confirms success. A merchant must only fulfill after its authenticated `GET /v1/orders/{order_ref}` reports `paid`, and must reconcile settlement and chargebacks separately.
- An unknown provider initiation error is **not automatically retried**. Investigate it in the provider dashboard first; otherwise a second payment might be created.

This service is a gateway *integration*, **not a PSP licence or bank core**. It is appropriate for a merchant that already has a provider agreement, not for offering unlicensed pooled-wallet custody or loans.

## 2. Regulatory and commercial gate (must be documented outside GitHub)

Before switching `SLICKK_GATEWAY_LIVE=true`:

1. Confirm the registered legal entity, its authorization/licence number, regulator or licensed sponsoring bank/PSP, approved product scope, geographical scope and conditions. Your approval to write code is not the same as a regulator-issued financial licence.
2. Confirm a signed commercial merchant agreement and **live SSLCOMMERZ merchant account** under the eligible entity, including chargeback/refund/settlement terms and merchant verification.
3. Check whether the deployment merely collects merchant payments (gateway model) or independently stores e-money/settles third-party funds. The latter may require separate Bangladesh Bank permission.
4. Obtain written sign-off from qualified Bangladesh payments counsel and your contracted provider; obtain a banking/lending agreement separately for any microloan operations.
5. Complete e-KYC/AML/CFT, sanctions, anti-fraud, complaints and data protection controls for the actual regulated activity, as applicable. Loans must not be enabled until the licensed lender has approved the product, affordability and underwriting process.

**Official references (verify against current amendments):**

- Bangladesh Bank PSD overview: https://www.bb.org.bd/en/index.php/financialsystems/paysystems
- BB PSP/PSO approval guidance: https://www.bb.org.bd/aboutus/regulationguideline/psd/pso_psp_03022019.pdf
- BB e-KYC 2026: https://www.bb.org.bd/mediaroom/circulars/brpd/mar112026brpd-108e.pdf
- BB e-Payment Credit 2026: https://www.bb.org.bd/mediaroom/circulars/brpd/sep062026brpd-117e.pdf
- SSLCOMMERZ v4: https://developer.sslcommerz.com/doc/v4/index.html

## 3. Infrastructure gate

- Choose an authorized provider's supported hosting jurisdiction. For customer/loan PII, confirm applicable Bangladesh data-localization requirements before selecting a data region; do not assume an overseas hosting provider qualifies.
- Separate staging and production organizations/projects, bank/gateway credentials, databases, DNS and secrets. Enforce HTTPS and least-privilege access.
- Provision PostgreSQL with encrypted storage, backups tested by restore, controlled schema migration, retention and security monitoring. **Never use ephemeral SQLite in production.**
- Harden the ingress with WAF + rate limiting, especially on `/v1/gateway/ipn` and `/v1/checkouts`; restrict merchant key to trusted server systems/IPs where feasible.
- Ensure trusted reverse proxy configuration, DDoS protection, log redaction (no gateway passwords, API keys, full gateway query strings, customer card/NID data), monitoring, alerting and incident response.
- Perform independent penetration testing, merchant/order-amount authorization review, provider-led acceptance testing and operational disaster-recovery rehearsal.
- Implement daily payment reconciliation with provider settlements, refund and chargeback management, dispute and customer-support workflows, reporting, audit trails and key rotation prior to public-money launch.
- Verify merchant price/amount from its own authenticated order/invoice database before creating checkouts. The current merchant API does not include an independent product catalogue.

This is a starter integration, **not production-certified infrastructure**. `create_all()` bootstraps the checkout database schema; replace with reviewed migrations before a managed production roll-out. Production deployment requires additional operational controls above.

## 4. Configuration

Copy `.env.example` into your hosting provider's **private** secrets configuration. Never commit `.env` or real credentials.

| Key | Staging | Live-approval candidate |
|---|---|---|
| `SLICKK_ENV` | `staging` | `production` |
| `SLICKK_ENABLE_CHECKOUTS` | `true` after sandbox credentials | `true` after all gates |
| `SLICKK_GATEWAY_LIVE` | `false` | `true` only after agreement |
| `SLICKK_REGULATORY_SIGNOFF` | `false` | `true` only after documented review |
| `SLICKK_PUBLIC_BASE_URL` | `https://staging.example.com` | Your approved HTTPS domain |
| `SLICKK_MERCHANT_API_KEY` | 32+ random chars | Different 64+ random chars |
| `SSLCOMMERZ_STORE_ID` | Provider sandbox ID | Provider live ID |
| `SSLCOMMERZ_STORE_PASSWORD` | Provider sandbox secret | Provider live secret |
| `DATABASE_URL` | Dedicated staging DB | `postgresql+psycopg://...` production PostgreSQL |

**Important:** `SLICKK_REGULATORY_SIGNOFF=true` is only a software guard and cannot demonstrate actual regulatory authorization. The project owner and provider remain responsible for verification.

Generate a random key locally (do **not** put it in chat):

```powershell
py -c "import secrets; print(secrets.token_urlsafe(48))"
```

Build and run the isolated service:

```bash
docker build -t slickk-pay-checkout .
docker run --rm --env-file .env -p 8000:8000 slickk-pay-checkout
```

Use a persistent managed PostgreSQL database for production; don't run SQLite under this command for actual payments.

`GET /healthz` confirms the process is alive; `GET /readyz` returns 503 if checkout is not enabled.

## 5. Merchant backend API (server-to-server)

`POST /v1/checkouts` with header `X-Slickk-Api-Key: <server-only-secret>`:

```json
{
  "order_ref": "INVOICE-2026-00001",
  "amount_bdt": "100.00",
  "product_name": "Software service",
  "product_category": "general",
  "customer_name": "Example Customer",
  "customer_email": "customer@example.com",
  "customer_phone": "01700000000",
  "customer_address": "Dhaka",
  "customer_city": "Dhaka",
  "customer_postcode": "1000"
}
```

Response includes `transaction_id`, `order_ref`, `status: pending_payment` and a provider `gateway_url`. The merchant then redirects its customer to that URL. Repeating the same order reference with the exact same data returns the existing checkout URL. Reusing it with different data returns HTTP 409.

`GET /v1/orders/{order_ref}` requires the same merchant API key. `paid` means provider-validated payment; `risk_review` is **not** safe to fulfill; `pending_payment` and `initiation_unknown` are not paid. This is *not* a settlement confirmation, and merchants must still reconcile payouts and resolve disputes.

`POST /v1/gateway/ipn` accepts SSLCOMMERZ form fields. It is public for provider callbacks, but cannot mark an order paid based only on the posted form; an independent provider validation call is required.

## 6. Test, readiness and non-goals

```bash
python -m unittest discover -s tests -v
python -m compileall -q app
```

Tests use an HTTPX mock transport and **cannot** prove connectivity, contract validity, real settlement, issuer behavior, or regulatory approval. Before customer launch, run sandbox end-to-end tests with your actual gateway sandbox account; confirm provider returns, IPN, retries and settlement reports; obtain written provider go-live clearance and complete the regulatory/operations gates.

No loans, loan approvals, wallet issuance, remittances, customer deposits or cross-border payouts are implemented by `app.live`. Those need separate licensed partnerships and controls.
