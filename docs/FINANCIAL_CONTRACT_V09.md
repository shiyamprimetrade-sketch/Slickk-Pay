# Slickk Pay v0.9 integration contract

Original implementation; no Shopno source or credentials copied. The uploaded Shopno Ltd archive contains 2,080 files, including billing-engine, gateway adapters, financial capability discovery, and deployment infrastructure. Its LICENSE reserves rights and grants no copying/modifying/redistribution permission. We use architecture observations, not proprietary source. Its PR #15 was draft in the supplied report.

**Gateway:** `GET /v1/capabilities` describes BDT hosted merchant checkout; wallets, loans, remittances, FX and direct gateways remain disabled. No regulatory authorization is inferred.

**IPN:** Duplicated/ambiguous URL-form keys or malformed escapes are rejected before server-to-server provider validation. Browser redirects cannot mark orders paid. Existing terminal-state audit and risk holds are retained.

**Provider net:** Migration 003 adds nullable `gateway_reported_net_poisha` and a constraint plus reconciliation-view field `gateway_reported_net_bdt`. This is provider-reported net, **not bank settlement**. Migrate isolated staging after backup, and independently reconcile gateway and bank statements. Disposable CI migration runs 001, 002, 003 twice; never point it at Render/production.

**Merchant signatures:** When `SLICKK_REQUIRE_SIGNED_ORDERS=true`, or on enabled production, merchant server signs `["slickk-order-v1", timestamp_string, order_ref, amount_poisha_integer, product_name, product_category]` as compact UTF-8 JSON using HMAC-SHA256. Send `X-Slickk-Order-Timestamp` (Unix seconds, ±300s) and `X-Slickk-Order-Signature` (`v1=` + lowercase hex). Use `app.contracts.sign_merchant_order` only on a trusted merchant server after checking authoritative prices; never put `SLICKK_ORDER_SIGNING_SECRET` in a browser, source code, GitHub, or chat. Use a separate 32+ character secret, not the gateway password.

**Go-live:** Render staging remains disabled. Test private rotated sandbox credentials, IPN deliverability and reconciliation. Independent bank/vendor approval, security testing, data residency, refunds/chargebacks, settlement evidence and monitoring are still outstanding. Do not merge draft PR as a production release.
