"""Strict money, canonical evidence and privacy primitives."""
import unittest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.ops.primitives import (
    Currency, Money, Finding, EvidenceEnvelope, EvidenceError, ConflictError,
    InvariantError, reference, safe_key, ascii_label, minor_from_bdt,
    bdt_from_minor, bounded_ratio, positive_minor, nonnegative_minor,
    timestamp, parse_utc, utc_iso, days_between, sha256, evidence_hash,
    canonical_json, redacted_reference, require_keys, safe_public_text,
    ensure_unique_references,
)

T = datetime(2026, 11, 3, 12, 30, tzinfo=timezone.utc)


class MoneyPrimitiveTests(unittest.TestCase):
    def test_valid_fixed_decimal_cases(self):
        for text, expected in (("0.01", 1), ("1", 100), ("1.0", 100),
                               ("100.00", 10000), ("999999.99", 99999999)):
            with self.subTest(text=text):
                self.assertEqual(minor_from_bdt(text), expected)
                self.assertEqual(minor_from_bdt(Decimal(text)), expected)
                self.assertEqual(minor_from_bdt(bdt_from_minor(expected)), expected)

    def test_reject_decimal_ambiguity(self):
        for item in (1.2, 1, True, None, "", "0", "-1", "0.00", "-0.10",
                     "1.234", "1e2", "1E+2", "01.00", "+1.00",
                     " 1.00", "1.00 ", "NaN", "Infinity", "1,000.00"):
            with self.subTest(item=item):
                with self.assertRaises(EvidenceError):
                    minor_from_bdt(item)

    def test_can_allow_zero_and_negative_for_adjustment_only(self):
        self.assertEqual(minor_from_bdt("0", allow_zero=True), 0)
        self.assertEqual(minor_from_bdt("-3.10", allow_negative=True), -310)
        with self.assertRaises(EvidenceError):
            minor_from_bdt("-3.10")

    def test_exact_bdt_serialization(self):
        self.assertEqual(bdt_from_minor(101), "1.01")
        self.assertEqual(bdt_from_minor(-105), "-1.05")
        self.assertEqual(bdt_from_minor(0), "0.00")
        with self.assertRaises(EvidenceError):
            bdt_from_minor(1.1)

    def test_reject_bool_minor(self):
        with self.assertRaises(EvidenceError):
            positive_minor(True)
        with self.assertRaises(EvidenceError):
            nonnegative_minor(False)

    def test_money_arithmetic(self):
        a = Money.from_bdt("10.25")
        b = Money.from_bdt("5.05")
        self.assertEqual((a + b).bdt, "15.30")
        self.assertEqual((a - b).bdt, "5.20")
        self.assertEqual((-b).bdt, "-5.05")
        self.assertEqual(a.as_dict(), {"amount": "10.25", "currency": "BDT"})

    def test_money_rejects_unsupported_currency(self):
        with self.assertRaises(EvidenceError):
            Money(100, "USD")

    def test_bounded_ratio(self):
        self.assertEqual(bounded_ratio(50, 200), Decimal("0.25"))
        with self.assertRaises(EvidenceError):
            bounded_ratio(201, 200)
        with self.assertRaises(EvidenceError):
            bounded_ratio(1, 0)


class EvidencePrimitiveTests(unittest.TestCase):
    def test_reference_accepts_known_safe_symbols(self):
        for value in ("order-1", "shop/a:b.c_1", "abc", "2026/11/03"):
            self.assertEqual(reference(value), value)

    def test_reference_rejects_control_unicode_and_empty(self):
        for value in ("", " a", "a ", "a\nb", "..", "রহিম", "x"*97, None, 9):
            with self.subTest(value=value):
                with self.assertRaises(EvidenceError):
                    reference(value)

    def test_safe_key_and_public_note(self):
        self.assertEqual(safe_key("risk_flag"), "risk_flag")
        self.assertEqual(safe_public_text("manual_review_required"), "manual_review_required")
        for bad in ("Contains Space", "5bad", "a/b", ""): 
            with self.assertRaises(EvidenceError):
                safe_key(bad)
        with self.assertRaises(EvidenceError):
            safe_public_text("Customer: Jane Doe")

    def test_ascii_label_rejects_whitespace_and_controls(self):
        self.assertEqual(ascii_label("Provider record"), "Provider record")
        with self.assertRaises(EvidenceError):
            ascii_label(" Provider record ")
        with self.assertRaises(EvidenceError):
            ascii_label("New\nline")

    def test_timestamp_normalization(self):
        local = datetime(2026,11,3,18,30,tzinfo=timezone(timedelta(hours=6)))
        self.assertEqual(timestamp(local), T)
        self.assertEqual(parse_utc("2026-11-03T12:30:00Z"), T)
        self.assertEqual(utc_iso(local), "2026-11-03T12:30:00Z")
        self.assertEqual(days_between(T,T+timedelta(days=2)),2)

    def test_timestamp_requires_timezone(self):
        with self.assertRaises(EvidenceError):
            timestamp(datetime(2026,11,3))
        with self.assertRaises(EvidenceError):
            parse_utc("bad date")
        with self.assertRaises(EvidenceError):
            days_between(T,T-timedelta(seconds=1))

    def test_hash_determinism_and_sorting(self):
        self.assertEqual(evidence_hash({"b":2,"a":1}), evidence_hash({"a":1,"b":2}))
        self.assertNotEqual(evidence_hash({"a":1}), evidence_hash({"a":2}))
        self.assertEqual(len(sha256(b"abc")),64)
        self.assertEqual(canonical_json({"b":2,"a":1}),b'{"a":1,"b":2}')

    def test_canonical_rejects_floats_and_invalid_types(self):
        for value in (1.1, Decimal("1.1"), object(), {"a": 1.2}, {2: "two"},
                      {"value": [1, {"bad": object()}]}):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(EvidenceError):
                    canonical_json(value)

    def test_canonical_depth_bound(self):
        value = 1
        for _ in range(20):
            value = [value]
        with self.assertRaises(EvidenceError):
            canonical_json(value)

    def test_envelope_hash_and_summary(self):
        item = EvidenceEnvelope("evidence-A", "provider_validation", T,
                                {"status":"validated", "amount_poisha":1000})
        self.assertTrue(item.verify())
        self.assertEqual(len(item.digest), 64)
        self.assertEqual(item.summary()["created_at"], "2026-11-03T12:30:00Z")

    def test_envelope_tamper_detection(self):
        payload={"accepted": True}
        item=EvidenceEnvelope("evidence-B", "verification", T, payload)
        payload["accepted"] = False
        self.assertFalse(item.verify())

    def test_redaction_omits_raw_identifier(self):
        original="customer-phone-01700000000"
        redacted=redacted_reference(original)
        self.assertTrue(redacted.startswith("sha256:"))
        self.assertNotIn("01700000000", redacted)
        self.assertEqual(redacted, redacted_reference(original))

    def test_findings_are_structured(self):
        finding=Finding("missing_statement", "error", "order-100", "manual_review")
        public=finding.as_dict()
        self.assertEqual(public["severity"], "error")
        self.assertNotIn("order-100", public["reference_digest"])
        with self.assertRaises(EvidenceError):
            Finding("unknown", "emergency", "order-100")

    def test_require_keys(self):
        require_keys({"a":1,"b":2}, ("a","b"))
        with self.assertRaises(EvidenceError):
            require_keys({"a":1}, ("a","b"))

    def test_unique_reference_guard(self):
        ensure_unique_references(("a","b","c"), field_name="order")
        with self.assertRaises(ConflictError):
            ensure_unique_references(("a","b","a"),field_name="order")


if __name__=="__main__":
    unittest.main()
