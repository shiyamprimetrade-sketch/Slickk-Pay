"""Signature key rotation, replay resistance, and non-networking outbox tests."""
import unittest
from datetime import datetime, timezone, timedelta

from app.ops.security import (
    SigningKey, SignedEnvelope, KeyRing, NonceRegistry, HttpsEndpointPolicy,
)
from app.ops.outbox import Outbox, DeliveryState, RetryPolicy
from app.ops.primitives import EvidenceError, PolicyError, ConflictError, NotFoundError

T=datetime(2026,11,3,12,0,tzinfo=timezone.utc)


def new_key(key_id="key-1", *, start=T-timedelta(days=1), end=T+timedelta(days=1), sign=True):
    return SigningKey(key_id,b"A"*64,start,end,sign)


class SigningTests(unittest.TestCase):
    def setUp(self):
        self.ring=KeyRing()
        self.ring.register(new_key(),make_current=True)
        self.payload={"event":"payment_validated", "reference":"payment-1", "amount_poisha":1250}

    def sign(self, *, nonce="nonce-1", at=T):
        return self.ring.sign(self.payload,purpose="merchant_notification",nonce=nonce,at=at)

    def test_sign_verify_roundtrip(self):
        envelope=self.sign()
        self.assertTrue(self.ring.verify(self.payload,purpose="merchant_notification",envelope=envelope,at=T))
        self.assertTrue(envelope.as_headers()["X-Slickk-Signature"].startswith("v1="))

    def test_modified_payload_is_rejected(self):
        envelope=self.sign()
        changed={**self.payload,"amount_poisha":1251}
        self.assertFalse(self.ring.verify(changed,purpose="merchant_notification",envelope=envelope,at=T))

    def test_wrong_signature_purpose_is_rejected(self):
        envelope=self.sign()
        self.assertFalse(self.ring.verify(self.payload,purpose="gateway_ipn",envelope=envelope,at=T))

    def test_signature_expires(self):
        envelope=self.sign()
        self.assertFalse(self.ring.verify(self.payload,purpose="merchant_notification",envelope=envelope,
                                          at=T+timedelta(seconds=300)))

    def test_signature_rejects_future_timestamp(self):
        envelope=self.sign(at=T+timedelta(hours=1))
        self.assertFalse(self.ring.verify(self.payload,purpose="merchant_notification",envelope=envelope,at=T))

    def test_key_rotation_old_signature_still_verifies(self):
        old=self.sign()
        self.ring.register(new_key("key-2"),make_current=True)
        latest=self.sign(nonce="nonce-2")
        self.assertEqual(latest.key_id,"key-2")
        self.assertTrue(self.ring.verify(self.payload,purpose="merchant_notification",envelope=old,at=T))

    def test_retired_key_cannot_issue_signatures(self):
        self.ring.retire("key-1",at=T)
        with self.assertRaises(PolicyError):
            self.sign()
        self.assertFalse(self.ring.public_manifest(at=T)["secrets_exposed"])

    def test_key_id_reuse_rejected(self):
        with self.assertRaises(ConflictError):
            self.ring.register(new_key())

    def test_expired_key_cannot_sign(self):
        ring=KeyRing()
        ring.register(new_key("expired",end=T-timedelta(seconds=1)),make_current=True)
        with self.assertRaises(PolicyError):
            ring.sign(self.payload,purpose="merchant_notification",nonce="nonce-A",at=T)

    def test_invalid_key_length_rejected(self):
        with self.assertRaises(EvidenceError):
            SigningKey("short",b"short",T,T+timedelta(days=1))

    def test_nonces_are_scoped_by_key(self):
        registry=NonceRegistry()
        expiry=T+timedelta(seconds=300)
        self.assertTrue(registry.consume(key_id="key-1",nonce="nonce-1",expires_at=expiry,now=T))
        self.assertFalse(registry.consume(key_id="key-1",nonce="nonce-1",expires_at=expiry,now=T))
        self.assertTrue(registry.consume(key_id="key-2",nonce="nonce-1",expires_at=expiry,now=T))

    def test_nonce_expires_and_can_be_used_after_cleanup(self):
        registry=NonceRegistry()
        self.assertTrue(registry.consume(key_id="key-1",nonce="nonce-1",
                                         expires_at=T+timedelta(seconds=1),now=T))
        self.assertTrue(registry.consume(key_id="key-1",nonce="nonce-1",
                                         expires_at=T+timedelta(seconds=10),now=T+timedelta(seconds=2)))

    def test_nonce_registry_full_fails_closed(self):
        registry=NonceRegistry(capacity=1)
        expiry=T+timedelta(hours=1)
        registry.consume(key_id="key-1",nonce="nonce-1",expires_at=expiry,now=T)
        with self.assertRaises(PolicyError):
            registry.consume(key_id="key-1",nonce="nonce-2",expires_at=expiry,now=T)

    def test_nonce_with_expired_signature_not_consumed(self):
        self.assertFalse(NonceRegistry().consume(key_id="key-1",nonce="n-1",
            expires_at=T,now=T))


class HttpsBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.policy=HttpsEndpointPolicy({"merchant.example.com"})

    def test_allow_expected_https_endpoint(self):
        self.assertEqual(self.policy.validate("https://merchant.example.com/webhooks/payments"),
                         "https://merchant.example.com/webhooks/payments")

    def test_reject_http_and_unlisted_domains(self):
        for url in ("http://merchant.example.com/hook", "https://evil.example.com/hook",
                    "https://merchant.example.com.evil.com/hook", "https://127.0.0.1/hook",
                    "https://merchant.example.com:8443/hook"):
            with self.subTest(url=url):
                with self.assertRaises(PolicyError):
                    self.policy.validate(url)

    def test_reject_endpoint_with_embedded_credentials(self):
        with self.assertRaises(PolicyError):
            self.policy.validate("https://u:pass@merchant.example.com/hook")

    def test_reject_secret_query_and_fragment(self):
        for url in ("https://merchant.example.com/hook?token=secret",
                    "https://merchant.example.com/hook#fragment"):
            with self.assertRaises(PolicyError):
                self.policy.validate(url)

    def test_internal_hosts_not_accepted_as_policy(self):
        for host in ("localhost", "127.0.0.1", "db.internal.local"):
            with self.assertRaises((EvidenceError,PolicyError)):
                HttpsEndpointPolicy({host})


class OutboxTests(unittest.TestCase):
    def setUp(self):
        self.policy=HttpsEndpointPolicy({"merchant.example.com"})
        self.out=Outbox(self.policy,retry_policy=RetryPolicy(max_attempts=3,initial_seconds=5),enabled=True)

    def enqueue(self, *, ref="event-A", amount=100):
        return self.out.enqueue(merchant_id="merchant-A",event_ref=ref,
                                event_type="payment_verified",
                                endpoint="https://merchant.example.com/hook",
                                payload={"amount_poisha":amount,"reference":"txn-A"},created_at=T)

    def test_enqueue_and_list_due(self):
        self.enqueue()
        due=self.out.list_due(merchant_id="merchant-A",at=T)
        self.assertEqual(len(due),1)
        self.assertEqual(due[0].state,DeliveryState.QUEUED)

    def test_disabled_by_default_cannot_be_leased(self):
        out=Outbox(self.policy)
        event=out.enqueue(merchant_id="merchant-A",event_ref="e1",event_type="payment_verified",
                          endpoint="https://merchant.example.com/hook",
                          payload={"status":"paid"},created_at=T)
        self.assertEqual(event.state,DeliveryState.DISABLED)
        with self.assertRaises(PolicyError):
            out.lease(event_ref="e1",merchant_id="merchant-A",at=T,lease_token="token-1")

    def test_event_reference_is_idempotent(self):
        first=self.enqueue()
        self.assertEqual(first,self.enqueue())
        self.assertEqual(self.out.stats(merchant_id="merchant-A")["event_count"],1)

    def test_conflicting_event_reference_rejected(self):
        self.enqueue()
        with self.assertRaises(ConflictError):
            self.enqueue(amount=200)

    def test_successful_acknowledgement(self):
        self.enqueue()
        leased=self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=T,
                              lease_token="token-1")
        self.assertEqual(leased.state,DeliveryState.LEASED)
        result=self.out.finish(merchant_id="merchant-A",event_ref="event-A",lease_token="token-1",
                                at=T+timedelta(seconds=1),status_code=204)
        self.assertEqual(result.state,DeliveryState.ACKNOWLEDGED)
        self.assertEqual(self.out.list_due(merchant_id="merchant-A",at=T),())

    def test_retry_after_http_500(self):
        self.enqueue()
        self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=T,lease_token="token-1")
        retry=self.out.finish(merchant_id="merchant-A",event_ref="event-A",lease_token="token-1",
                               at=T+timedelta(seconds=1),status_code=500)
        self.assertEqual(retry.state,DeliveryState.RETRY_SCHEDULED)
        self.assertEqual(self.out.list_due(merchant_id="merchant-A",at=T),())
        self.assertEqual(len(self.out.list_due(merchant_id="merchant-A",at=T+timedelta(minutes=5))),1)

    def test_token_mismatch_rejected(self):
        self.enqueue()
        self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=T,lease_token="token-1")
        with self.assertRaises(PolicyError):
            self.out.finish(merchant_id="merchant-A",event_ref="event-A",lease_token="wrong",
                            at=T+timedelta(seconds=1),status_code=200)

    def test_second_worker_cannot_steal_active_lease(self):
        self.enqueue()
        self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=T,lease_token="token-1")
        with self.assertRaises(ConflictError):
            self.out.lease(event_ref="event-A",merchant_id="merchant-A",
                           at=T+timedelta(seconds=2),lease_token="token-2")

    def test_expired_lease_cannot_be_acknowledged(self):
        self.enqueue()
        self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=T,lease_token="token-1",lease_seconds=1)
        with self.assertRaises(PolicyError):
            self.out.finish(merchant_id="merchant-A",event_ref="event-A",lease_token="token-1",
                            at=T+timedelta(seconds=10),status_code=200)

    def test_retries_are_bounded(self):
        self.enqueue()
        now=T
        for attempt in range(3):
            token=f"token-{attempt}"
            self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=now,lease_token=token)
            record=self.out.finish(merchant_id="merchant-A",event_ref="event-A",
                lease_token=token,at=now+timedelta(seconds=1),status_code=503)
            now=record.next_attempt_at
        self.assertEqual(record.state,DeliveryState.EXHAUSTED)
        with self.assertRaises(PolicyError):
            self.out.lease(event_ref="event-A",merchant_id="merchant-A",at=now,lease_token="token-4")

    def test_merchant_outbox_isolation(self):
        self.enqueue()
        with self.assertRaises(NotFoundError):
            self.out.get("event-A",merchant_id="merchant-B")
        self.assertEqual(self.out.list_due(merchant_id="merchant-B",at=T),())

    def test_public_outbox_stats_no_delivery_claim(self):
        self.enqueue()
        stats=self.out.stats(merchant_id="merchant-A")
        self.assertFalse(stats["network_delivery_implemented"])
        self.assertEqual(stats["event_count"],1)

    def test_retry_policy_is_deterministic(self):
        retry=RetryPolicy()
        self.assertEqual(retry.next_delay(event_ref="event-A",attempt=1),
                         retry.next_delay(event_ref="event-A",attempt=1))


if __name__=="__main__":
    unittest.main()
