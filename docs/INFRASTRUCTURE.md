# Infrastructure and operations checkpoint

The only new infrastructure is `.github/workflows/pg-sandbox-cycle002.yml`, which provisions temporary PostgreSQL 16 in GitHub Actions and installs a pinned TypeScript compiler for contract tests. The database name is `slickk_ci_test` on loopback. The workflow password is fictional and exists only inside its disposable CI service. The runner tests migration 004 repeatability, journal integrity, rollback, concurrent idempotency and synthetic authorization nonce replay.

**Not deployed:** The `app.pgsandbox` lab, inspection API, TypeScript SDK, bank ledger or loan engine. Existing `render.yaml` remains unchanged, with checkouts disabled by default. No Kubernetes, Terraform, Redis or durable messaging broker is introduced. The outbox only maintains durable records; it does not send notifications over any external network.

Before any financial staging operation: rotate exposed provider and database credentials, connect Render through an authorized account, review the independent partner authorization, confirm data residency, record security-review approval, test backup/restore and reconcile actual sandbox provider statements. Never infer real money movement from CI passing.
