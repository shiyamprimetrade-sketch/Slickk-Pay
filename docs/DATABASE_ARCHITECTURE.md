# Cycle 002 financial sandbox database

## Isolation and migration

`SandboxStore` accepts PostgreSQL only when `SLICKK_PG_SANDBOX=true`, the host is `localhost`/`127.0.0.1`/`::1`, and the database name is precisely `slickk_ci_test`. Production environment and live-gateway flags cause initialization to fail. Named local SQLite files are allowed only with `local_test=True` for deterministic unit tests.

`migrations/004_pg_sandbox_cycle002.sql` is generated from the checked-in SQLAlchemy Core model and is idempotent for a **fresh disposable lab**. It creates the `s2_*` tables and PostgreSQL UPDATE/DELETE-rejection triggers on immutable journals, postings, security events, cash state history and used synthetic authorization nonces. The install code also validates the current database name from PostgreSQL before applying DDL. Never run migration 004 on the merchant-checkout database.

## Tables

- `s2_accounts`: synthetic participant balances, owner, kind and version.
- `s2_chain`: locked singleton hash-chain head and journal count.
- `s2_journals` / `s2_postings`: append-only balanced accounting records.
- `s2_cash_requests` / `s2_cash_inventory` / `s2_cash_history`: fictitious cash workflow and handover history.
- `s2_money_events`: durable velocity-policy evidence.
- `s2_security_events`: hashed, redacted operator findings.
- `s2_outbox`: retryable, lease-guarded notification metadata.
- `s2_auth_nonces`: one-time synthetic authorization replay protection.
- `s2_reconciliation`: internal posting/balance evidence, not bank settlement.
- `s2_disputes`: reserved schema for future dispute workflows.

All balances use BIGINT minor units, and accounts except the fictional issuer cannot become negative. Global head lock serializes posting order. The test harness verifies the journal, account balances, replay behavior and rollback after an injected exception.

## Important limitations

This is not a production bank ledger. There are no reviewed recovery point objectives, production backups, failover tests, data residency signoff, migration governance, external audit notarization, real identity verification or provider account settlement. `metadata.create_all` is acceptable only in the **guarded disposable sandbox**. A production migration framework and scoped database roles would require a separate approval and review.
