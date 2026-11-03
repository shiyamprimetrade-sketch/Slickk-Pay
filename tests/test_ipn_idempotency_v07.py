"""Regression: an IPN must not be acknowledged as verified if its val_id differs.

All gateway traffic is mocked; no production credentials or actual payments.
"""
import unittest
from tests import test_live


class IPNIdempotencyTests(unittest.TestCase):
    setUp = test_live.LiveCheckoutTests.setUp
    checkout = test_live.LiveCheckoutTests.checkout
    send_ipn = test_live.LiveCheckoutTests.send_ipn

    def test_paid_duplicate_with_conflicting_validation_id_is_unverified(self):
        self.checkout()
        self.assertEqual(self.send_ipn().json()["status"], "paid")
        calls = len(self.gateway_calls)
        mismatch = self.send_ipn(val_id="forged-provider-id-2")
        self.assertEqual(mismatch.status_code, 200)
        self.assertEqual(mismatch.json()["verified"], False)
        self.assertEqual(len(self.gateway_calls), calls)
        self.assertEqual(self.send_ipn().json()["verified"], True)

    def test_risk_review_duplicate_with_conflicting_validation_id_is_unverified(self):
        self.checkout()
        self.validation_override = {"risk_level": "1"}
        self.assertEqual(self.send_ipn().json()["status"], "risk_review")
        calls = len(self.gateway_calls)
        mismatch = self.send_ipn(val_id="forged-provider-id-3")
        self.assertEqual(mismatch.status_code, 200)
        self.assertEqual(mismatch.json()["verified"], False)
        self.assertEqual(len(self.gateway_calls), calls)
        self.assertEqual(self.send_ipn().json()["verified"], True)


if __name__ == "__main__":
    unittest.main()
