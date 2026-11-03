-- Slickk Pay Cycle 002: DISPOSABLE POSTGRESQL LAB SCHEMA ONLY

-- Never apply to Render, production or an existing regulated financial database.

-- Target: loopback PostgreSQL database named slickk_ci_test.

-- All balances are fictitious integer poisha.


CREATE TABLE IF NOT EXISTS s2_accounts (
	account_id VARCHAR(96) NOT NULL, 
	owner_id VARCHAR(96) NOT NULL, 
	kind VARCHAR(40) NOT NULL, 
	balance BIGINT NOT NULL, 
	frozen BOOLEAN NOT NULL, 
	version BIGINT NOT NULL, 
	created_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (account_id), 
	CONSTRAINT s2_balance_nonnegative CHECK (balance >= 0 OR kind = 'sim_issuer'), 
	CONSTRAINT s2_version_nonnegative CHECK (version >= 0)
);

CREATE TABLE IF NOT EXISTS s2_auth_nonces (
	nonce_digest VARCHAR(64) NOT NULL, 
	actor_id VARCHAR(96) NOT NULL, 
	scope VARCHAR(40) NOT NULL, 
	key_id VARCHAR(32) NOT NULL, 
	expires_at VARCHAR(35) NOT NULL, 
	accepted_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (nonce_digest)
);

CREATE TABLE IF NOT EXISTS s2_chain (
	id SERIAL NOT NULL, 
	latest_hash VARCHAR(64) NOT NULL, 
	latest_sequence BIGINT NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT s2_one_chain CHECK (id = 1)
);

CREATE TABLE IF NOT EXISTS s2_disputes (
	case_id VARCHAR(96) NOT NULL, 
	request_id VARCHAR(96) NOT NULL, 
	actor_id VARCHAR(96) NOT NULL, 
	reason_code VARCHAR(48) NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	evidence_digest VARCHAR(64), 
	opened_at VARCHAR(35) NOT NULL, 
	updated_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (case_id), 
	CONSTRAINT s2_dispute_state CHECK (state IN ('open','review','resolved','rejected'))
);

CREATE TABLE IF NOT EXISTS s2_journals (
	sequence SERIAL NOT NULL, 
	event_id VARCHAR(96) NOT NULL, 
	idempotency_key VARCHAR(96) NOT NULL, 
	operation VARCHAR(50) NOT NULL, 
	request_digest VARCHAR(64) NOT NULL, 
	previous_hash VARCHAR(64) NOT NULL, 
	entry_hash VARCHAR(64) NOT NULL, 
	created_at VARCHAR(35) NOT NULL, 
	actor_id VARCHAR(96) NOT NULL, 
	PRIMARY KEY (sequence), 
	UNIQUE (event_id), 
	UNIQUE (idempotency_key), 
	UNIQUE (entry_hash)
);

CREATE TABLE IF NOT EXISTS s2_money_events (
	id SERIAL NOT NULL, 
	account_id VARCHAR(96) NOT NULL, 
	operation VARCHAR(40) NOT NULL, 
	amount BIGINT NOT NULL, 
	event_id VARCHAR(96) NOT NULL, 
	occurred_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (event_id)
);

CREATE TABLE IF NOT EXISTS s2_outbox (
	message_id VARCHAR(96) NOT NULL, 
	event_id VARCHAR(96) NOT NULL, 
	destination VARCHAR(96) NOT NULL, 
	payload_digest VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	state VARCHAR(16) NOT NULL, 
	attempts INTEGER NOT NULL, 
	next_attempt_at VARCHAR(35) NOT NULL, 
	lease_until VARCHAR(35), 
	lease_token VARCHAR(64), 
	created_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (message_id), 
	CONSTRAINT s2_outbox_event_destination UNIQUE (event_id, destination), 
	CONSTRAINT s2_outbox_attempts CHECK (attempts >= 0), 
	CONSTRAINT s2_outbox_state CHECK (state IN ('ready','leased','delivered','dead'))
);

CREATE TABLE IF NOT EXISTS s2_reconciliation (
	recon_id VARCHAR(96) NOT NULL, 
	period VARCHAR(10) NOT NULL, 
	account_id VARCHAR(96) NOT NULL, 
	opening BIGINT NOT NULL, 
	debits BIGINT NOT NULL, 
	credits BIGINT NOT NULL, 
	closing BIGINT NOT NULL, 
	observed BIGINT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	evidence_digest VARCHAR(64) NOT NULL, 
	created_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (recon_id), 
	CONSTRAINT s2_recon_account_period UNIQUE (period, account_id), 
	CONSTRAINT s2_recon_state CHECK (status IN ('matching','exception'))
);

CREATE TABLE IF NOT EXISTS s2_security_events (
	sequence SERIAL NOT NULL, 
	actor_id VARCHAR(96) NOT NULL, 
	action VARCHAR(45) NOT NULL, 
	entity_digest VARCHAR(64) NOT NULL, 
	reason VARCHAR(60) NOT NULL, 
	previous_hash VARCHAR(64) NOT NULL, 
	event_hash VARCHAR(64) NOT NULL, 
	recorded_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (sequence), 
	UNIQUE (event_hash)
);

CREATE TABLE IF NOT EXISTS s2_cash_inventory (
	agent_account VARCHAR(96) NOT NULL, 
	cash BIGINT NOT NULL, 
	cash_ceiling BIGINT NOT NULL, 
	updated_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (agent_account), 
	CONSTRAINT s2_cash_bounds CHECK (cash >= 0 AND cash_ceiling >= 0 AND cash <= cash_ceiling), 
	FOREIGN KEY(agent_account) REFERENCES s2_accounts (account_id)
);

CREATE TABLE IF NOT EXISTS s2_cash_requests (
	request_id VARCHAR(96) NOT NULL, 
	customer_account VARCHAR(96) NOT NULL, 
	agent_account VARCHAR(96) NOT NULL, 
	agent_commission_account VARCHAR(96) NOT NULL, 
	revenue_account VARCHAR(96) NOT NULL, 
	escrow_account VARCHAR(96), 
	kind VARCHAR(12) NOT NULL, 
	amount BIGINT NOT NULL, 
	fee BIGINT NOT NULL, 
	commission BIGINT NOT NULL, 
	tax BIGINT NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	nonce_digest VARCHAR(64) NOT NULL, 
	request_digest VARCHAR(64) NOT NULL, 
	expires_at VARCHAR(35) NOT NULL, 
	created_at VARCHAR(35) NOT NULL, 
	last_event VARCHAR(96), 
	handover_digest VARCHAR(64), 
	PRIMARY KEY (request_id), 
	CONSTRAINT s2_cash_kind CHECK (kind IN ('cash_in','cash_out')), 
	CONSTRAINT s2_cash_amounts CHECK (amount > 0 AND fee >= 0 AND commission >= 0 AND tax >= 0), 
	CONSTRAINT s2_cash_state CHECK (state IN ('awaiting','reserved','customer_confirmed','completed','cancelled','expired','disputed')), 
	FOREIGN KEY(customer_account) REFERENCES s2_accounts (account_id), 
	FOREIGN KEY(agent_account) REFERENCES s2_accounts (account_id), 
	FOREIGN KEY(agent_commission_account) REFERENCES s2_accounts (account_id), 
	FOREIGN KEY(revenue_account) REFERENCES s2_accounts (account_id), 
	FOREIGN KEY(escrow_account) REFERENCES s2_accounts (account_id), 
	UNIQUE (handover_digest)
);

CREATE TABLE IF NOT EXISTS s2_postings (
	event_id VARCHAR(96) NOT NULL, 
	line_index INTEGER NOT NULL, 
	account_id VARCHAR(96) NOT NULL, 
	direction VARCHAR(6) NOT NULL, 
	amount BIGINT NOT NULL, 
	CONSTRAINT s2_posting_position UNIQUE (event_id, line_index), 
	CONSTRAINT s2_posting_direction CHECK (direction IN ('debit','credit')), 
	CONSTRAINT s2_posting_positive CHECK (amount > 0), 
	FOREIGN KEY(event_id) REFERENCES s2_journals (event_id) ON DELETE RESTRICT, 
	FOREIGN KEY(account_id) REFERENCES s2_accounts (account_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS s2_cash_history (
	sequence SERIAL NOT NULL, 
	request_id VARCHAR(96) NOT NULL, 
	old_state VARCHAR(24), 
	new_state VARCHAR(24) NOT NULL, 
	reason VARCHAR(60) NOT NULL, 
	recorded_at VARCHAR(35) NOT NULL, 
	PRIMARY KEY (sequence), 
	FOREIGN KEY(request_id) REFERENCES s2_cash_requests (request_id)
);

CREATE INDEX IF NOT EXISTS s2_accounts_owner ON s2_accounts (owner_id, kind);

CREATE INDEX IF NOT EXISTS s2_auth_actor ON s2_auth_nonces (actor_id, accepted_at);

CREATE INDEX IF NOT EXISTS s2_disputes_request ON s2_disputes (request_id);

CREATE INDEX IF NOT EXISTS s2_journals_time ON s2_journals (created_at);

CREATE INDEX IF NOT EXISTS s2_money_events_actor_time ON s2_money_events (account_id, occurred_at);

CREATE INDEX IF NOT EXISTS s2_outbox_due ON s2_outbox (state, next_attempt_at);

CREATE INDEX IF NOT EXISTS s2_security_actor_time ON s2_security_events (actor_id, recorded_at);

CREATE INDEX IF NOT EXISTS s2_cash_customer ON s2_cash_requests (customer_account, created_at);

CREATE INDEX IF NOT EXISTS s2_cash_agent ON s2_cash_requests (agent_account, state);

CREATE INDEX IF NOT EXISTS s2_postings_account ON s2_postings (account_id, event_id);

CREATE INDEX IF NOT EXISTS s2_cash_history_request ON s2_cash_history (request_id, sequence);

CREATE OR REPLACE FUNCTION s2_reject_immutable_change()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'immutable fictional ledger audit record';
END;
$$ LANGUAGE plpgsql;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 's2_journals_immutable_guard') THEN
        CREATE TRIGGER s2_journals_immutable_guard
            BEFORE UPDATE OR DELETE ON s2_journals
            FOR EACH ROW EXECUTE FUNCTION s2_reject_immutable_change();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 's2_postings_immutable_guard') THEN
        CREATE TRIGGER s2_postings_immutable_guard
            BEFORE UPDATE OR DELETE ON s2_postings
            FOR EACH ROW EXECUTE FUNCTION s2_reject_immutable_change();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 's2_security_events_immutable_guard') THEN
        CREATE TRIGGER s2_security_events_immutable_guard
            BEFORE UPDATE OR DELETE ON s2_security_events
            FOR EACH ROW EXECUTE FUNCTION s2_reject_immutable_change();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 's2_cash_history_immutable_guard') THEN
        CREATE TRIGGER s2_cash_history_immutable_guard
            BEFORE UPDATE OR DELETE ON s2_cash_history
            FOR EACH ROW EXECUTE FUNCTION s2_reject_immutable_change();
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                   WHERE tgname = 's2_auth_nonces_immutable_guard') THEN
        CREATE TRIGGER s2_auth_nonces_immutable_guard
            BEFORE UPDATE OR DELETE ON s2_auth_nonces
            FOR EACH ROW EXECUTE FUNCTION s2_reject_immutable_change();
    END IF;
END;
$$;

