# v0.6 disposable PostgreSQL migration rehearsal

The GitHub Actions job tests the actual merchant checkout SQL migration on a **disposable PostgreSQL 16 service container**. It does not connect to a Render database, production, Bangladesh Bank or SSLCOMMERZ. A hard-coded fictional password belongs to the temporary GitHub CI service only.

The CI test creates the existing merchant_checkouts baseline schema and applies the migration twice. It inserts and updates a fictitious checkout and verifies the database trigger's state events, the internal reconciliation view, BDT precision, timestamps and absence of sensitive card-number columns. The service database is discarded with the CI runner.

## Fail-closed target restrictions

The runner requires both CI=true and SLICKK_EPHEMERAL_DB_TEST=true and accepts only a localhost PostgreSQL database named slickk_ci_test on port 5432. It must **never** be repointed to production or Render staging. No payment calls or funds movement occur.

## Remaining steps

This does not validate actual Render migration, settlement, a regulated merchant authorisation, or a genuine gateway sandbox transaction. Before the separately approved staging migration, rotate credentials disclosed in chat; independently confirm operating entity, merchant product scope and settlement arrangements; back up the staging database; review database permissions and migration; deploy with financial flags disabled. For production, require secure webhook validation, gateway reporting, bank settlement reconciliation, disputes/refunds, monitoring and security review.

See docs/PROVIDER_CONFIG_AND_MIGRATION.md and docs/RENDER_STAGING_DEPLOYMENT.md.
