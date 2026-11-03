"""SQLAlchemy Core schema shared by isolated SQLite tests and guarded PostgreSQL lab.

Transactions and journals use integer poisha. Never merge these tables into the
existing merchant checkout database, and never infer any regulated permissions.
"""
from __future__ import annotations
from sqlalchemy import (MetaData, Table, Column, String, Integer, BigInteger, Boolean,
    ForeignKey, CheckConstraint, UniqueConstraint, Index, Text)

metadata = MetaData()
accounts = Table("s2_accounts", metadata,
    Column("account_id", String(96), primary_key=True),
    Column("owner_id", String(96), nullable=False),
    Column("kind", String(40), nullable=False),
    Column("balance", BigInteger, nullable=False, default=0),
    Column("frozen", Boolean, nullable=False, default=False),
    Column("version", BigInteger, nullable=False, default=0),
    Column("created_at", String(35), nullable=False),
    CheckConstraint("balance >= 0 OR kind = 'sim_issuer'", "s2_balance_nonnegative"),
    CheckConstraint("version >= 0", "s2_version_nonnegative"))
Index("s2_accounts_owner", accounts.c.owner_id, accounts.c.kind)

chain = Table("s2_chain", metadata,
    Column("id", Integer, primary_key=True),
    Column("latest_hash", String(64), nullable=False),
    Column("latest_sequence", BigInteger, nullable=False, default=0),
    CheckConstraint("id = 1", "s2_one_chain"))

journals = Table("s2_journals", metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("event_id", String(96), unique=True, nullable=False),
    Column("idempotency_key", String(96), unique=True, nullable=False),
    Column("operation", String(50), nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("entry_hash", String(64), nullable=False, unique=True),
    Column("created_at", String(35), nullable=False),
    Column("actor_id", String(96), nullable=False))
Index("s2_journals_time", journals.c.created_at)

postings = Table("s2_postings", metadata,
    Column("event_id", String(96), ForeignKey("s2_journals.event_id", ondelete="RESTRICT"), nullable=False),
    Column("line_index", Integer, nullable=False),
    Column("account_id", String(96), ForeignKey("s2_accounts.account_id", ondelete="RESTRICT"), nullable=False),
    Column("direction", String(6), nullable=False),
    Column("amount", BigInteger, nullable=False),
    UniqueConstraint("event_id", "line_index", name="s2_posting_position"),
    CheckConstraint("direction IN ('debit','credit')", "s2_posting_direction"),
    CheckConstraint("amount > 0", "s2_posting_positive"))
Index("s2_postings_account", postings.c.account_id, postings.c.event_id)

requests = Table("s2_cash_requests", metadata,
    Column("request_id", String(96), primary_key=True),
    Column("customer_account", String(96), ForeignKey("s2_accounts.account_id"), nullable=False),
    Column("agent_account", String(96), ForeignKey("s2_accounts.account_id"), nullable=False),
    Column("agent_commission_account", String(96), ForeignKey("s2_accounts.account_id"), nullable=False),
    Column("revenue_account", String(96), ForeignKey("s2_accounts.account_id"), nullable=False),
    Column("escrow_account", String(96), ForeignKey("s2_accounts.account_id"), nullable=True),
    Column("kind", String(12), nullable=False),
    Column("amount", BigInteger, nullable=False),
    Column("fee", BigInteger, nullable=False),
    Column("commission", BigInteger, nullable=False),
    Column("tax", BigInteger, nullable=False, default=0),
    Column("state", String(24), nullable=False),
    Column("nonce_digest", String(64), nullable=False),
    Column("request_digest", String(64), nullable=False),
    Column("expires_at", String(35), nullable=False),
    Column("created_at", String(35), nullable=False),
    Column("last_event", String(96)),
    Column("handover_digest", String(64), unique=True, nullable=True),
    CheckConstraint("kind IN ('cash_in','cash_out')", "s2_cash_kind"),
    CheckConstraint("amount > 0 AND fee >= 0 AND commission >= 0 AND tax >= 0", "s2_cash_amounts"),
    CheckConstraint("state IN ('awaiting','reserved','customer_confirmed','completed','cancelled','expired','disputed')", "s2_cash_state"))
Index("s2_cash_customer", requests.c.customer_account, requests.c.created_at)
Index("s2_cash_agent", requests.c.agent_account, requests.c.state)

cash_history = Table("s2_cash_history", metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("request_id", String(96), ForeignKey("s2_cash_requests.request_id"), nullable=False),
    Column("old_state", String(24), nullable=True),
    Column("new_state", String(24), nullable=False),
    Column("reason", String(60), nullable=False),
    Column("recorded_at", String(35), nullable=False))
Index("s2_cash_history_request", cash_history.c.request_id, cash_history.c.sequence)

cash_inventory = Table("s2_cash_inventory", metadata,
    Column("agent_account", String(96), ForeignKey("s2_accounts.account_id"), primary_key=True),
    Column("cash", BigInteger, nullable=False, default=0),
    Column("cash_ceiling", BigInteger, nullable=False, default=0),
    Column("updated_at", String(35), nullable=False),
    CheckConstraint("cash >= 0 AND cash_ceiling >= 0 AND cash <= cash_ceiling", "s2_cash_bounds"))

money_events = Table("s2_money_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("account_id", String(96), nullable=False),
    Column("operation", String(40), nullable=False),
    Column("amount", BigInteger, nullable=False),
    Column("event_id", String(96), nullable=False, unique=True),
    Column("occurred_at", String(35), nullable=False))
Index("s2_money_events_actor_time", money_events.c.account_id, money_events.c.occurred_at)

security_events = Table("s2_security_events", metadata,
    Column("sequence", Integer, primary_key=True, autoincrement=True),
    Column("actor_id", String(96), nullable=False),
    Column("action", String(45), nullable=False),
    Column("entity_digest", String(64), nullable=False),
    Column("reason", String(60), nullable=False),
    Column("previous_hash", String(64), nullable=False),
    Column("event_hash", String(64), nullable=False, unique=True),
    Column("recorded_at", String(35), nullable=False))
Index("s2_security_actor_time", security_events.c.actor_id, security_events.c.recorded_at)

outbox = Table("s2_outbox", metadata,
    Column("message_id", String(96), primary_key=True),
    Column("event_id", String(96), nullable=False),
    Column("destination", String(96), nullable=False),
    Column("payload_digest", String(64), nullable=False),
    Column("payload", Text, nullable=False),
    Column("state", String(16), nullable=False),
    Column("attempts", Integer, nullable=False, default=0),
    Column("next_attempt_at", String(35), nullable=False),
    Column("lease_until", String(35), nullable=True),
    Column("lease_token", String(64), nullable=True),
    Column("created_at", String(35), nullable=False),
    UniqueConstraint("event_id", "destination", name="s2_outbox_event_destination"),
    CheckConstraint("attempts >= 0", "s2_outbox_attempts"),
    CheckConstraint("state IN ('ready','leased','delivered','dead')", "s2_outbox_state"))
Index("s2_outbox_due", outbox.c.state, outbox.c.next_attempt_at)

auth_nonces = Table("s2_auth_nonces", metadata,
    Column("nonce_digest", String(64), primary_key=True),
    Column("actor_id", String(96), nullable=False),
    Column("scope", String(40), nullable=False),
    Column("key_id", String(32), nullable=False),
    Column("expires_at", String(35), nullable=False),
    Column("accepted_at", String(35), nullable=False))
Index("s2_auth_actor", auth_nonces.c.actor_id, auth_nonces.c.accepted_at)

cases = Table("s2_disputes", metadata,
    Column("case_id", String(96), primary_key=True),
    Column("request_id", String(96), nullable=False),
    Column("actor_id", String(96), nullable=False),
    Column("reason_code", String(48), nullable=False),
    Column("state", String(24), nullable=False),
    Column("evidence_digest", String(64), nullable=True),
    Column("opened_at", String(35), nullable=False),
    Column("updated_at", String(35), nullable=False),
    CheckConstraint("state IN ('open','review','resolved','rejected')", "s2_dispute_state"))
Index("s2_disputes_request", cases.c.request_id)

reconciliation = Table("s2_reconciliation", metadata,
    Column("recon_id", String(96), primary_key=True),
    Column("period", String(10), nullable=False),
    Column("account_id", String(96), nullable=False),
    Column("opening", BigInteger, nullable=False),
    Column("debits", BigInteger, nullable=False),
    Column("credits", BigInteger, nullable=False),
    Column("closing", BigInteger, nullable=False),
    Column("observed", BigInteger, nullable=False),
    Column("status", String(20), nullable=False),
    Column("evidence_digest", String(64), nullable=False),
    Column("created_at", String(35), nullable=False),
    UniqueConstraint("period", "account_id", name="s2_recon_account_period"),
    CheckConstraint("status IN ('matching','exception')", "s2_recon_state"))

KIND_VALUES = frozenset({"customer", "agent_float", "agent_commission", "merchant",
    "platform_revenue", "platform_treasury", "escrow", "sim_issuer"})

ALL_TABLES = tuple(metadata.tables)
