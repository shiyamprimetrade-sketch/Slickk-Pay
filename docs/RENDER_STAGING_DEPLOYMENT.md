# Render staging integration (no real money)

**Status: configuration prepared; deployment NOT performed.**

`render.yaml` provisions a staging-only Docker web service and a **free, non-production** PostgreSQL database. Its service deploys `app.live:app`, **not the original demo** (`app.main:app`). Checkout, gateway-live, and regulatory-signoff flags all default to `false`. `/healthz` may return HTTP 200 while `/readyz` returns HTTP 503, *by design*. No payments, wallets, or loans become operational upon deployment.

## Security first

- **Rotate any Render API key pasted into chat**: revoke it and generate another directly in the Render dashboard. Never paste the replacement in chat, tickets, code, docs, or GitHub Actions.
- This repo has no Render API key, SSLCOMMERZ credential, or customer's personal information. Use Render's encrypted environment variables for credentials.
- Connect Render to GitHub through an authorized account. Selecting a Blueprint and confirming resources is a separate account action, and may incur charges if selecting paid plans.
- **Do not turn on `SLICKK_GATEWAY_LIVE` or `SLICKK_ENABLE_CHECKOUTS` simply because hosting succeeds.** Live go/no-go requires the operator's documented merchant agreement, relevant BB/partner authorization, independent security review, settlement reconciliation, and vendor acceptance.
- Verify data residency with the regulated partner before uploading any actual customer data to Render. Do not upload customer PII to the sample staging database.

## Steps after the code is reviewed and merged to main

1. In Render, connect GitHub account and choose **New > Blueprint**. Select `shiyamprimetrade-sketch/Slickk-Pay` and `render.yaml`. Confirm it is reading `main` with the reviewed commit.
2. Review the resource summary and free-plan availability in your Render workspace before approving the setup. Render free PostgreSQL instances are **not** suitable for durable production financial data.
3. If prompted for `SLICKK_PUBLIC_BASE_URL`, use the **actual HTTPS service URL** shown by Render, e.g. `https://<assigned-host>.onrender.com` (without a trailing slash). If a hostname has not been assigned, keep checkout disabled, finish deployment, and then update the variable in Render.
4. Deploy; check `/healthz` returns `{"ok":true,"service":"checkout-api"}` and `/readyz` returns 503. Check `/` says `enabled:false`, `gateway:"sandbox"`, `wallets:"disabled"`, `loans:"disabled"`.
5. Optionally run `python scripts/smoke_staging.py https://<assigned-host>.onrender.com` from a terminal. It must report a disabled service with a healthy process.
6. Keep `autoDeployTrigger: off` for staging to avoid unreviewed code changes being deployed without review.

## Production architecture — NOT enabled by the Blueprint

Production needs its own paid PostgreSQL, restore tests, migrations, replay/abuse protection, incident response, independent penetration testing, merchant order-price authorization, refunds/disputes/chargebacks, and gateway settlement reconciliation. `SLICKK_REGULATORY_SIGNOFF=true` alone is *not* evidence of regulator approval. Real lending requires a separate licensed financial partner, credit-policy signoff, customer disclosure and complete compliance controls.

Source: https://render.com/docs/blueprint-spec (Blueprint syntax, `sync: false`, `fromDatabase`, and deployment settings).
