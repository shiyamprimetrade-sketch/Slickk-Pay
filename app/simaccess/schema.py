"""Versioned, local-only SQLite schema for synthetic identity and request records.

This is NOT a financial ledger and has no balance-affecting tables or postings.
All keys are synthetic. Existing PostgreSQL ledgers remain entirely separate.
"""
from __future__ import annotations

SCHEMA_VERSION = 5
SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS lab_schema_version (
    version INTEGER PRIMARY KEY CHECK(version BETWEEN 1 AND 999),
    created_at INTEGER NOT NULL CHECK(created_at > 0)
);
CREATE TABLE IF NOT EXISTS lab_actors (
    actor_id TEXT PRIMARY KEY CHECK(actor_id LIKE 'sim_%'),
    role TEXT NOT NULL CHECK(role IN ('customer','agent','merchant','operator')),
    label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 60),
    salt TEXT NOT NULL,
    pin_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active','frozen','closed')),
    created_at INTEGER NOT NULL,
    locked_until INTEGER NOT NULL DEFAULT 0,
    bad_attempts INTEGER NOT NULL DEFAULT 0 CHECK(bad_attempts >= 0),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0)
);
CREATE TABLE IF NOT EXISTS lab_devices (
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    device_digest TEXT NOT NULL,
    label TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('trusted','revoked')),
    enrolled_at INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    PRIMARY KEY(actor_id,device_digest)
);
CREATE TABLE IF NOT EXISTS lab_sessions (
    token_digest TEXT PRIMARY KEY CHECK(length(token_digest) = 64),
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    device_digest TEXT NOT NULL,
    role TEXT NOT NULL,
    issued_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    last_used_at INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('active','revoked','expired')),
    FOREIGN KEY(actor_id, device_digest) REFERENCES lab_devices(actor_id, device_digest)
);
CREATE INDEX IF NOT EXISTS lab_sessions_actor ON lab_sessions(actor_id,state);
CREATE TABLE IF NOT EXISTS lab_replay (
    purpose TEXT NOT NULL,
    nonce_digest TEXT NOT NULL CHECK(length(nonce_digest) = 64),
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    expires_at INTEGER NOT NULL,
    accepted_at INTEGER NOT NULL,
    PRIMARY KEY(purpose,nonce_digest)
);
CREATE TABLE IF NOT EXISTS lab_rate_limits (
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    bucket INTEGER NOT NULL,
    counter INTEGER NOT NULL CHECK(counter >= 0),
    PRIMARY KEY(actor_id,action,bucket)
);
CREATE TABLE IF NOT EXISTS lab_snapshots (
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    sample_account_id TEXT NOT NULL CHECK(sample_account_id LIKE 'sim_%'),
    sample_balance_poisha INTEGER NOT NULL CHECK(sample_balance_poisha >= 0),
    sample_currency TEXT NOT NULL DEFAULT 'BDT' CHECK(sample_currency='BDT'),
    updated_at INTEGER NOT NULL,
    PRIMARY KEY(actor_id,sample_account_id)
);
CREATE TABLE IF NOT EXISTS lab_activity (
    activity_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    sample_direction TEXT NOT NULL CHECK(sample_direction IN ('in','out')),
    amount_poisha INTEGER NOT NULL CHECK(amount_poisha > 0),
    status TEXT NOT NULL CHECK(status IN ('sample_paid','sample_cancelled','sample_pending')),
    description TEXT NOT NULL,
    occurred_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS lab_activity_actor_time ON lab_activity(actor_id,occurred_at DESC);
CREATE TABLE IF NOT EXISTS lab_quotes (
    quote_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    operation TEXT NOT NULL CHECK(operation IN ('transfer','cash_in','cash_out','merchant_payment')),
    counterpart_id TEXT NOT NULL,
    principal_poisha INTEGER NOT NULL CHECK(principal_poisha > 0),
    fee_poisha INTEGER NOT NULL CHECK(fee_poisha >= 0),
    total_poisha INTEGER NOT NULL CHECK(total_poisha > 0),
    rate_version TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('quoted','expired','cancelled','reviewed')),
    source_ref TEXT NOT NULL,
    UNIQUE(owner_id,source_ref)
);
CREATE INDEX IF NOT EXISTS lab_quotes_owner_time ON lab_quotes(owner_id,created_at DESC);
CREATE TABLE IF NOT EXISTS lab_requests (
    request_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    quote_id TEXT NOT NULL UNIQUE REFERENCES lab_quotes(quote_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reviewed','cancelled','expired')),
    accepted_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    no_financial_posting INTEGER NOT NULL DEFAULT 1 CHECK(no_financial_posting = 1),
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0)
);
CREATE TABLE IF NOT EXISTS lab_request_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL REFERENCES lab_requests(request_id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL,
    happened_at INTEGER NOT NULL,
    event_digest TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lab_request_events_request ON lab_request_events(request_id,happened_at);
CREATE TABLE IF NOT EXISTS lab_cash_checklists (
    request_id TEXT PRIMARY KEY REFERENCES lab_requests(request_id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    cash_available INTEGER NOT NULL DEFAULT 0 CHECK(cash_available IN (0,1)),
    customer_present INTEGER NOT NULL DEFAULT 0 CHECK(customer_present IN (0,1)),
    warnings_acknowledged INTEGER NOT NULL DEFAULT 0 CHECK(warnings_acknowledged IN (0,1)),
    handover_status TEXT NOT NULL DEFAULT 'not_authorized' CHECK(handover_status='not_authorized'),
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lab_cash_ack (
    request_id TEXT PRIMARY KEY REFERENCES lab_requests(request_id) ON DELETE RESTRICT,
    customer_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    agent_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    customer_ref_digest TEXT,
    agent_ref_digest TEXT,
    status TEXT NOT NULL CHECK(status IN ('waiting','both_reviewed','cancelled')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    handover_authorized INTEGER NOT NULL DEFAULT 0 CHECK(handover_authorized=0),
    CHECK(customer_id!=agent_id)
);
CREATE INDEX IF NOT EXISTS lab_cash_ack_agent ON lab_cash_ack(agent_id,status);
CREATE TABLE IF NOT EXISTS lab_support (
    case_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    category TEXT NOT NULL CHECK(category IN ('question','privacy','incorrect_quote','suspected_fraud')),
    safe_description TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','closed')),
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS lab_support_actor ON lab_support(actor_id,created_at DESC);
CREATE TABLE IF NOT EXISTS lab_outbox (
    event_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL REFERENCES lab_actors(actor_id) ON DELETE RESTRICT,
    kind TEXT NOT NULL,
    safe_body TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending','acknowledged','suppressed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts>=0),
    next_attempt_at INTEGER NOT NULL,
    UNIQUE(actor_id,kind,event_id)
);
CREATE TABLE IF NOT EXISTS lab_audit_head (
    id INTEGER PRIMARY KEY CHECK(id=1),
    sequence INTEGER NOT NULL CHECK(sequence>=0),
    hash TEXT NOT NULL CHECK(length(hash)=64)
);
CREATE TABLE IF NOT EXISTS lab_audit (
    sequence INTEGER PRIMARY KEY CHECK(sequence > 0),
    event_id TEXT NOT NULL UNIQUE,
    actor_digest TEXT NOT NULL CHECK(length(actor_digest)=64),
    event_type TEXT NOT NULL,
    event_digest TEXT NOT NULL CHECK(length(event_digest)=64),
    previous_hash TEXT NOT NULL CHECK(length(previous_hash)=64),
    entry_hash TEXT NOT NULL CHECK(length(entry_hash)=64),
    created_at INTEGER NOT NULL
);
CREATE TRIGGER IF NOT EXISTS lab_audit_immutable_update BEFORE UPDATE ON lab_audit
BEGIN SELECT RAISE(ABORT, 'immutable simulated audit'); END;
CREATE TRIGGER IF NOT EXISTS lab_audit_immutable_delete BEFORE DELETE ON lab_audit
BEGIN SELECT RAISE(ABORT, 'immutable simulated audit'); END;
CREATE TRIGGER IF NOT EXISTS lab_request_events_immutable_update BEFORE UPDATE ON lab_request_events
BEGIN SELECT RAISE(ABORT, 'immutable simulated request event'); END;
CREATE TRIGGER IF NOT EXISTS lab_request_events_immutable_delete BEFORE DELETE ON lab_request_events
BEGIN SELECT RAISE(ABORT, 'immutable simulated request event'); END;
"""

REQUIRED_TABLES = frozenset({
    "lab_schema_version", "lab_actors", "lab_devices", "lab_sessions", "lab_replay",
    "lab_rate_limits", "lab_snapshots", "lab_activity", "lab_quotes", "lab_requests",
    "lab_request_events", "lab_cash_checklists", "lab_cash_ack", "lab_support", "lab_outbox", "lab_audit_head", "lab_audit",
})


def schema_identity() -> str:
    import hashlib
    return hashlib.sha256(SCHEMA_SQL.encode()).hexdigest()
