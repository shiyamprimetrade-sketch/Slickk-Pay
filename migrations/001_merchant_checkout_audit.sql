-- Slickk Pay v0.4, PostgreSQL upgrade to the existing merchant_checkouts.
-- No parallel mutable transaction table, no card PAN, no customer PII.
-- Apply manually after approved backup, with a migration-only database role.
BEGIN;
ALTER TABLE merchant_checkouts
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
-- Leave older rows NULL rather than invent historical timestamps.
ALTER TABLE merchant_checkouts ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE merchant_checkouts ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;
CREATE INDEX IF NOT EXISTS idx_checkout_state_created ON merchant_checkouts (state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_checkout_created_at ON merchant_checkouts (created_at DESC);
CREATE TABLE IF NOT EXISTS merchant_checkout_state_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    checkout_id VARCHAR(32) NOT NULL REFERENCES merchant_checkouts(id) ON DELETE RESTRICT,
    previous_state VARCHAR(32),
    current_state VARCHAR(32) NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_checkout_events_checkout ON merchant_checkout_state_events (checkout_id, observed_at DESC);
CREATE OR REPLACE FUNCTION slickk_checkout_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_slickk_checkout_updated_at ON merchant_checkouts;
CREATE TRIGGER trg_slickk_checkout_updated_at BEFORE UPDATE ON merchant_checkouts
    FOR EACH ROW EXECUTE FUNCTION slickk_checkout_updated_at();
CREATE OR REPLACE FUNCTION slickk_checkout_state_audit()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO merchant_checkout_state_events (checkout_id, previous_state, current_state)
        VALUES (NEW.id, NULL, NEW.state);
    ELSIF OLD.state IS DISTINCT FROM NEW.state THEN
        INSERT INTO merchant_checkout_state_events (checkout_id, previous_state, current_state)
        VALUES (NEW.id, OLD.state, NEW.state);
    END IF;
    RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_slickk_checkout_state_audit ON merchant_checkouts;
CREATE TRIGGER trg_slickk_checkout_state_audit AFTER INSERT OR UPDATE OF state ON merchant_checkouts
    FOR EACH ROW EXECUTE FUNCTION slickk_checkout_state_audit();
-- This is internal reconciliation, not a regulator-approved report.
-- Gateway 'paid' status does not itself prove funds settled in a bank.
CREATE OR REPLACE VIEW merchant_checkout_reconciliation AS
SELECT id AS tran_id, order_ref,
       (amount_poisha::NUMERIC / 100)::NUMERIC(12, 2) AS amount_bdt,
       'BDT'::VARCHAR(3) AS currency,
       state AS gateway_status, val_id, bank_tran_id,
       created_at, updated_at
FROM merchant_checkouts;
-- Grant SELECT on this view to a separately provisioned read-only login.
COMMIT;
