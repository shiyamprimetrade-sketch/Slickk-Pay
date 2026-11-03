-- Provider-validation net is not bank settlement. Apply to backed-up staging first.
BEGIN;
ALTER TABLE merchant_checkouts ADD COLUMN IF NOT EXISTS gateway_reported_net_poisha BIGINT;
DO $$
BEGIN
 IF NOT EXISTS (
   SELECT 1 FROM pg_constraint
   WHERE conname='merchant_checkout_gateway_net_bounds'
   AND conrelid='merchant_checkouts'::regclass
 ) THEN
   ALTER TABLE merchant_checkouts ADD CONSTRAINT merchant_checkout_gateway_net_bounds
   CHECK (gateway_reported_net_poisha IS NULL OR
         (gateway_reported_net_poisha>0 AND gateway_reported_net_poisha<=amount_poisha));
 END IF;
END $$;
CREATE OR REPLACE VIEW merchant_checkout_reconciliation AS
SELECT id AS tran_id,order_ref,
       (amount_poisha::NUMERIC/100)::NUMERIC(12,2) AS amount_bdt,
       'BDT'::VARCHAR(3) AS currency,state AS gateway_status,
       val_id,bank_tran_id,created_at,updated_at,
       (gateway_reported_net_poisha::NUMERIC/100)::NUMERIC(12,2) AS gateway_reported_net_bdt
FROM merchant_checkouts;
COMMIT;
