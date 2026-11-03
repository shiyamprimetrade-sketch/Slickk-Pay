-- v0.8: rejected IPN security events (metadata only). No raw payloads, PII or tokens.
-- Apply to isolated staging only after backup and change-control approval.
BEGIN;
CREATE TABLE IF NOT EXISTS merchant_checkout_ipn_security_events (
    event_id VARCHAR(32) PRIMARY KEY,
    checkout_id VARCHAR(32) NOT NULL REFERENCES merchant_checkouts(id) ON DELETE RESTRICT,
    existing_state VARCHAR(32) NOT NULL,
    reason VARCHAR(48) NOT NULL,
    status_hint VARCHAR(16) NOT NULL,
    val_id_digest VARCHAR(64),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_slickk_ipn_security_checkout_time
    ON merchant_checkout_ipn_security_events(checkout_id, recorded_at DESC);
COMMIT;
