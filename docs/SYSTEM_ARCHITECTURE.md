# Slickk Pay — Current architecture (Cycle 002)

## Operational separation

The existing `app.live:app` is the hosted-checkout integration candidate and remains disabled by default. The previous fictional-wallet implementation lives in `app.core` and `app.sandboxfinance`, and the v1.0 read-only operations toolkit lives in `app.ops`. Cycle 002 adds `app.pgsandbox` as a **separate internal laboratory**. Its FastAPI inspector is not imported or mounted by `app.live`, and its database target guard rejects remote PostgreSQL hosts.

```text
                  External regulated financial networks
                    [NOT connected by Cycle 002]
                               X
                               X
merchant backend -> isolated app.live (checkout gateway integration; OFF)

local synthetic issuer -> app.pgsandbox LedgerService -> guarded PostgreSQL lab
                            |            |                 |
                       cash workflow   audit/outbox    reconciliation
                            |            |                 |
                            +---------s2_* tables---------+
                                     |
                      read-only opt-in inspector
                                     |
                         strict TypeScript SDK
```

## Invariants

1. All test values are integer poisha. There is no float-backed account balance.
2. A journal contains equal positive debit and credit totals and at least two posting lines.
3. The posting, balance updates, transaction hash chain and associated cash state are written in one transaction.
4. Idempotency identity includes the canonical request digest. Reuse with altered contents is rejected.
5. PostgreSQL writers lock one journal head row and sorted account rows under SERIALIZABLE isolation. Serialization and deadlock failures must trigger a **whole-transaction** retry under the same idempotency key.
6. Cash-out requires synthetic customer initiation and confirmation, then separate agent handover attestation. An ambiguous post-confirmation timeout is held for dispute, not silently refunded.
7. Commission and customer fee assumptions are pilot hypotheses, not approved tariffs.
8. The durable outbox stores bounded, non-PII fictional metadata; its receiver must deduplicate at-least-once deliveries.
9. A successful internal reconciliation is not SSLCOMMERZ validation or verified bank settlement.
10. All tooling is sandbox-only; none exposes real deposit or credit functions.

## Deployment boundary

The new SQL migration `004_pg_sandbox_cycle002.sql` is for `slickk_ci_test` on loopback only. The existing merchant migration sequence `001`–`003` is untouched. A separate CI workflow creates a disposable PostgreSQL 16 instance and tests journal, row locks, authorization replay and rollback. No staging or production migration is performed.
