# Architecture Decision Records — Cycle 002

### ADR-002-01 — Retain Python ledger interface, introduce guarded PostgreSQL lab

**Decision:** Build a separate transactional PostgreSQL-capable *sandbox* using SQLAlchemy Core without replacing the Cycle 001 SQLite simulator or the existing SSLCOMMERZ checkout app.

**Reason:** The prior source and tests are Python-based, and PostgreSQL locking is the next unverified technical dependency. Introducing Go before profiling would split authoritative accounting logic unnecessarily. **Consequence:** Go service deferred; isolate all new tables with `s2_*` prefixes and strict local database guards.

### ADR-002-02 — Durable journal and outbox, no network delivery

**Decision:** Journal, account updates, cash state changes and retry metadata share database transactions. Outbox records have one-time leases and bounded retries. **Reason:** A failed callback or worker crash must not create duplicate financial value. **Consequence:** External delivery/receiving systems and real settlement remain future work.

### ADR-002-03 — TypeScript for read-only boundary

**Decision:** Introduce a dependency-light, strictly checked TypeScript SDK that treats every server response as unknown until parsed. **Reason:** This establishes a reusable mobile/web contract without replacing tested accounting rules. **Consequence:** SDK fees are educational sample assumptions, not an alternative source of authoritative tariffs or balances.

### ADR-002-04 — No automatic cash reversal after ambiguous handover

**Decision:** Once the customer approves the handover, timeout becomes a dispute holding state with escrow intact. **Reason:** Automatically releasing electronic value while physical cash might already have been paid creates value duplication. **Consequence:** Manual, evidence-driven resolution is required; no real cash handling is implemented.

### ADR-002-05 — PostgreSQL migration execution restricted to local CI

**Decision:** Migration 004 is accepted only for a localhost database named `slickk_ci_test` under explicit sandbox flags. **Reason:** Avoid accidental production schema mutation. **Consequence:** Real deployment needs a separately reviewed migration and governance path, not reuse of this CI runner.
