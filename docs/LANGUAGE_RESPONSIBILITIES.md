# Programming language responsibility map

**Python (implemented):** merchant-checkout adapter, original sandbox modules, Cycle 002 PostgreSQL-capable fictional double-entry ledger, cash and transfer operations, risk policies, reconciliation, outbox, read-only inspection, synthetic compliance experiments.

**SQL (implemented):** PostgreSQL sandbox schema and immutability triggers in migration 004. Existing merchant checkout migrations 001–003 are preserved.

**TypeScript (implemented):** strict, read-only, synthetic ledger inspection client; amount formatting; validation of received API evidence; Bangla/English presentation helpers. No direct POST operation or authoritative balance calculation.

**YAML (implemented):** GitHub Actions disposable PostgreSQL and TypeScript contract-test workflow. Existing Render Blueprint remains disabled by default.

**Go (not introduced):** conditional future ledger hot path, subject to benchmarking and migration design. Do not duplicate posting rules merely to use Go.

**Kotlin/Swift/React Native/NestJS/Next.js/Rust/Terraform/Kubernetes (not introduced by this cycle):** future modules subject to signed-off dependencies, costs and measurable technical need. Existing working code in other languages must be preserved.
