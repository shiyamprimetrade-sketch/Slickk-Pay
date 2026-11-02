# Slickk Pay & Credit — product and regulatory launch plan

**Positioning:** Inclusive, low-bandwidth payments and partner-financed essential-payment credit for Bangladesh. Distinct from Slickk agency, Slickk-OS, Slickk AI and Prime International.

## Benchmark products and takeaways

| Product references | Adopt the workflow pattern; not their brand, licence, rails or code |
|---|---|
| bKash, Nagad | Mobile-first Bangladeshi wallet experience, merchant acceptance and bill payments |
| Stripe | Developer APIs, merchant checkout, refunds, reconciliation and webhooks |
| PayPal | Customer and merchant dispute-management patterns |
| Payoneer | International freelancer/business payout workflows |
| Wise | FX transparency and remittance-fee disclosure |
| Western Union, Remitly, Taptap Send | Remittance tracking and legally authorised local payout partnerships |
| bKash + City Bank | Split payment distribution and legally authorised lender underwriting |

**Business design hypothesis (not evidence of demand):** Bangladesh freelancers, small merchants, and low-income bill payers may benefit from one clear ledger-backed app with visible prices, Bangla language, and partner credit. Validate with interviews before building paid features.

## Commercial approach (partner first)

1. **Launch as a technology provider**, not as a bank. Create a separate fintech legal entity and secure local legal advice. Verify permissible brand/business descriptors before public launch.
2. **Domestic payments:** sign an agreement with a Bangladesh Bank-licensed PSP/PSO, bank or approved merchant acquiring partner. The partner, not the unlicensed software demo, owns regulated settlement flows as dictated by agreements and licensing.
3. **Small loans:** integrate a licensed bank (or appropriate authorised lender) and let that institution own credit policy, eligibility checks, credit reporting, loan documents, collection, and disbursement, as applicable. Develop the user front end only with a signed approved product programme.
4. **International remittance:** work with authorised remittance and local bank/MFS payout networks. Do not independently offer FX conversion, cross-border transfers or customer-fund custody.
5. Consider independent PSP or digital-bank licensing only after funding, governance, regulatory consultation, and repeatable product economics.

## Roadmap and objective completion criteria

### P0 — Local sandbox: IMPLEMENTED
- FastAPI prototype, responsive web app, mock BDT transactions, accounting, idempotency, credit fee quotation, non-cash bill credit simulation, automated tests.
- Completion criterion: all automated tests pass; full ledger sums to zero; error conditions reject properly; demo disclaimer visible.

### P1 — Partner-ready pilot infrastructure: NOT IMPLEMENTED
- Business registration, counsel review, actual partner agreement and permission, secure production hosting in reviewed jurisdiction, independent security audit, access control/MFA, BFIU/BB compliant e-KYC, AML/CFT and PEP/sanctions screening, consumer consent, fraud rules, limits, complaints/refunds, audit logging, automated reconciliation.
- Completion criterion: documented regulatory permissions, partner sign-off, penetration test remediated, settlement reconciliation proven against partner sandbox, 100% required compliance checks passing.

### P2 — Bank-sponsored small bill credit: NOT IMPLEMENTED
- Focus on specified essential payment categories; bank-approved underwriting and borrower affordability, transparent disclosure and consent, limits, CIB obligations, reporting, and real settlement with approved billers.
- Bangladesh Bank's Sept 6 2026 e-Payment Credit circular requires *banks* to pilot for at least 6 months before commercial launch. Partner and regulatory requirements determine whether this product can be offered at all.
- Completion criterion: banking partner authorisation and board-approved PPG, six-month bank pilot, audit evidence and BB notifications where required.

### P3 — Inward remittances: NOT IMPLEMENTED
- Partner-led international inflows to authorised local accounts; FX quotes/fees from authorised provider; reversals, complaint channels, source-of-funds checks, sanctions screening, payout reconciliation.
- Completion criterion: authorised partner live certification and supported transfer corridors.

### P4 — Licensing and expansion: NOT IMPLEMENTED
- Assess standalone PSP/PSO or bank licence route, cost, governance and capital; do not claim regulated capabilities without the licence.

## Technical production architecture (target, not implemented)

- **Mobile clients:** Android + mobile web, bilingual Bangla/English, accessibility, offline-safe display of read-only history.
- **API:** API gateway and BFF, OAuth/OIDC, device binding, transaction-level step-up authentication.
- **Ledger:** audited immutable event journal, double-entry, high-availability SQL, reconciliation jobs and approval workflows.
- **Payments:** partner-specific adaptors, callback signature validation, transactional outbox, refunds, dispute intake, cut-off handling and settlement reconciliation.
- **Credit:** lender decision endpoint, credit docs & consent, loan servicing & delinquency handling controlled by partner, regulator-approved collections.
- **Compliance:** e-KYC, sanctions/PEP and AML monitoring, limits, data minimisation, encryption/KMS, monitored access, suspicious transaction escalation and retention.
- **Security:** independent audit, OWASP ASVS and MASVS checks, periodic penetration tests, key rotation, least privilege, DR simulations, observability and incident response.
- **Data residency:** regulatory/legal review for data storage in Bangladesh, including the specific e-Payment Credit circular's localisation instruction.

## Evidence and references

Bangladesh Bank e-Payment Credit Circular BRPD-1 no.17, Sep 6 2026: https://www.bb.org.bd/mediaroom/circulars/brpd/sep062026brpd-117e.pdf

Bangladesh Bank e-KYC revision effective Sep 1 2026: https://www.bb.org.bd/mediaroom/circulars/brpd/mar112026brpd-108e.pdf

Bangladesh Bank Digital Bank Guidelines, Version 2: https://www.bb.org.bd/aboutus/regulationguideline/brpd/digitalbank_version-2_english.pdf

Bangladesh Bank MFS Regulations 2022: https://www.bb.org.bd/aboutus/regulationguideline/psd/mfs_regulations_2022.pdf

bKash/City Bank loan architecture: https://www.bkash.com/en/products-services/loan

**No regulatory approval, real-money connection, loan underwriting or live deployment has been obtained by this prototype.**
