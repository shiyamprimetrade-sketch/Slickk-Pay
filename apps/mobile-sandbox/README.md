# Slickk Pay LAB — Android-first mobile sandbox (Cycle 003)

This **React Native / Expo app is a fictional-data prototype**. It is not the Slickk Pay live merchant checkout API, a banking app, an agent-money application, a real wallet, or a regulated payment provider. **It cannot post, confirm, queue, retry, or settle actual money.** It does not use SSLCOMMERZ or any network secret. All persons, cash, balances, invoices, transactions and notification records are synthetic fixtures.

## What is implemented

- Customer, agent and merchant demo personas with isolated sample accounts and activity.
- BDT accounting previews in integer poisha with proposed (unapproved) fees and transparent total debit.
- Fee quote preparation and local review as immutable drafts; no backend payment-confirmation action.
- Cash-in/out tabletop and agent float examples; physical cash handover remains unverified and cannot be approved by a single agent.
- Example QR payload parser restricted to the `slickkpaylab://` scheme; external payment QR schemes are rejected.
- Bangla/English UI, privacy masking, low-bandwidth rendering, accessibility labels, timeout/lock policy, offline-safe recovery.
- Sample merchant invoices, receipts with prominent **NOT PROOF OF PAYMENT** disclaimer, support drafts, notifications and read-only dashboards.

## Development prerequisites

- Node.js 22.13 or later.
- Android tooling / Expo CLI for a physical or emulator test. Expo SDK 57 is the conservative compatibility choice for Expo Go during the SDK 58 transition.
- Internet access to install npm dependencies (not required for the pure TypeScript core tests when `tsc` is installed globally).

```sh
cd apps/mobile-sandbox
npm install
npm run test:core
npx tsc -p tsconfig.json --noEmit
npm start
```

For a physical Android phone, follow the Expo CLI on-screen instructions. An exported JavaScript bundle is **not an APK** and a successful TypeScript compile does **not** prove on-device behavior. No APK or installed-device verification is claimed by this repository until it is actually built and tested.

## Privileged operator key boundary

Cycle 002's `clients/inspection-sdk` uses an intentionally privileged `X-Sim-Operator-Key` for an **isolated operator-only inspection API**. This mobile app does not import it, and never stores or embeds that key. A customer/agent server API requires separate authentication, authorization, KYC and permission design before real data can be displayed. Until then, only local synthetic fixtures are available.

## Offline and data-minimization contract

The prototype never persists authoritative balances, does not include a credential manager for real accounts, and will not replay money-changing intents after an offline period. Only non-sensitive appearance settings are eligible for future persistence. Do not input actual NID, OTP, PIN, production keys, real customer phone numbers, bank transactions or personal information into the prototype.

## Limitations and acceptance

`npm run test:core` validates pure TypeScript business and UI-state policy (including integer arithmetic, duplicate references, cross-persona isolation, agent/cash proof boundaries, secure QR parsing, localized disclosures, deterministic offline recovery, and denied money movement). The GitHub mobile workflow also checks React Native types and Android JavaScript bundle export. Neither test validates a native APK, real regulatory permission, production gateway integration, screen-reader use on devices, or actual bank settlement.

## Key source locations

- `src/core/*.ts` — portable, strict TypeScript domain, session, risk and view-model logic.
- `src/ui/*.tsx` — React Native components and sample screens.
- `App.tsx` — persona selection, navigation and role-safe demo app shell.
- `test/*.test.mjs` — Node.js automated test suite.
- `tsconfig.core.json` — standalone core check independent of native packages.
- `tsconfig.json` — full Expo/React Native TSX check when dependencies are installed.
