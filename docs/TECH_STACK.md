# Slickk Pay — Technology stack (Cycle 002)

This is a factual description of **implemented** components, not a promise of production deployment.

| Area | Actual code | Current maturity |
| --- | --- | --- |
| Merchant gateway adapter | Python 3, FastAPI, HTTPX, SQLAlchemy | SSLCOMMERZ mock-tested; live checkout disabled |
| Fictional internal finance | Python, SQLAlchemy Core, integer poisha | Cycle 002 transactional sandbox |
| Existing fictional ledger | Python, SQLite | Cycle 001 test bench, preserved |
| Reporting and audit | Python, SQLAlchemy, exact integer arithmetic | Lab-only |
| Database | PostgreSQL 16 in disposable GitHub Actions CI; SQLite local tests | No live financial database connected |
| UI contract client | Strict TypeScript 5.8.3, native Fetch, no runtime dependencies | Read-only fictional inspection SDK |
| Existing HTML/CSS | Static existing merchant sandbox pages | Preserved |
| Docker and Render | Existing Python container and disabled Blueprint | No new deployment |
| Continuous integration | GitHub Actions, Python unittest, Node test runner | Cycle 002 adds PostgreSQL/TypeScript CI |

**Not implemented:** NestJS backend, React Native customer or agent application, Go ledger service, Kotlin biometric integration, Swift UI, Redis, Kafka, a production bank core, live loans, real KYC or bank rails. These remain future, explicitly gated engineering options.

## Technology selection

Cycle 002 keeps SQLAlchemy and Python for the ledger because they exist in the tested Slickk Pay environment. PostgreSQL row locks and SERIALIZABLE transactions are exercised in disposable CI to build evidence for a future production review. The TypeScript SDK validates a read-only sandbox boundary; it does not reimplement money movement. Go is **deferred** until a measured ledger hot path or a separate operational boundary demonstrates sufficient benefit to justify another deployed service.

References: [PostgreSQL transaction retries](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html), [SQLAlchemy PostgreSQL dialect and isolation](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html).
