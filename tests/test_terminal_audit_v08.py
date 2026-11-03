"""Terminal-state immutability and redacted audit tests. Gateway calls are mocked."""
import hashlib
import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.live import Checkout, IPNSecurityEvent
from tests import test_live


class TerminalStateAuditTests(unittest.TestCase):
    setUp = test_live.LiveCheckoutTests.setUp
    checkout = test_live.LiveCheckoutTests.checkout
    send_ipn = test_live.LiveCheckoutTests.send_ipn

    def _set_state(self, state):
        engine = create_engine(self.db_url)
        with engine.begin() as conn:
            conn.execute(Checkout.__table__.update().where(Checkout.id == self.transaction_id).values(state=state))
        engine.dispose()

    def _assert_state_and_audit(self, expected_state, reason, raw_id):
        engine = create_engine(self.db_url)
        with Session(engine) as session:
            row = session.scalar(select(Checkout.state).where(Checkout.id == self.transaction_id))
            events = session.scalars(select(IPNSecurityEvent).where(IPNSecurityEvent.checkout_id == self.transaction_id)).all()
        engine.dispose()
        self.assertEqual(row, expected_state)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.reason, reason)
        self.assertEqual(event.val_id_digest, hashlib.sha256(raw_id.encode()).hexdigest())
        self.assertNotEqual(event.val_id_digest, raw_id)

    def _assert_terminal_locked(self, state):
        self.checkout()
        self._set_state(state)
        before = len(self.gateway_calls)
        token = "test-valid-reference-001"
        r = self.send_ipn(val_id=token, status="VALID")
        self.assertEqual(r.status_code, 200)
        self.assertIs(r.json()["verified"], False)
        self.assertEqual(len(self.gateway_calls), before)
        self._assert_state_and_audit(state, "terminal_state_blocked", token)

    def test_failed_terminal_is_immutable(self):
        self._assert_terminal_locked("failed")

    def test_cancelled_terminal_is_immutable(self):
        self._assert_terminal_locked("cancelled")

    def test_mismatched_paid_reference_is_logged_redacted(self):
        self.checkout()
        self.assertEqual(self.send_ipn().json()["status"], "paid")
        before = len(self.gateway_calls)
        raw_id = "untrusted-token-XX"
        response = self.send_ipn(val_id=raw_id)
        self.assertIs(response.json()["verified"], False)
        self.assertEqual(len(self.gateway_calls), before)
        self._assert_state_and_audit("paid", "terminal_reference_or_status_mismatch", raw_id)

    def test_spoofed_cancel_callback_does_not_mark_pending_order_cancelled(self):
        self.checkout()
        r = self.send_ipn(status="CANCELLED")
        self.assertIs(r.json()["verified"], False)
        engine = create_engine(self.db_url)
        with engine.connect() as conn:
            state = conn.execute(select(Checkout.state).where(Checkout.id == self.transaction_id)).scalar_one()
        engine.dispose()
        self.assertEqual(state, "pending_payment")
        self.assertEqual(len(self.gateway_calls), 1)


if __name__ == "__main__":
    unittest.main()
