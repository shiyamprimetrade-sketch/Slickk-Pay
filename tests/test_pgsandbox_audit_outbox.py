"""Outbox leases and redacted synthetic security/audit proofs."""
import tempfile
import unittest
from pathlib import Path
from app.pgsandbox import SandboxStore, LedgerService
from app.pgsandbox.audit import SecurityAudit, LedgerAuditor
from app.pgsandbox.outbox import DurableOutbox
from app.pgsandbox.errors import Conflict, InvalidValue, AuthorizationError, StateError

class AuditOutboxTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="sim-audit-");self.addCleanup(t.cleanup)
        self.store=SandboxStore("sqlite+pysqlite:///"+str(Path(t.name)/"test.db"),local_test=True)
        self.addCleanup(self.store.dispose)
        self.ledger=LedgerService(self.store)
        self.ledger.open_account("sim_issuer_primary","sim_owner_issuer","sim_issuer")
        self.ledger.open_account("sim_customer_alpha","sim_owner_alpha","customer")
        self.event=self.ledger.transfer("sim_issuer_primary","sim_customer_alpha",10000,
                                        key="issue:audit00001",actor="sim_operator_admin")
        self.audit=SecurityAudit(self.store)
        self.outbox=DurableOutbox(self.store,max_attempts=2)

    def test_redacted_security_chain(self):
        self.audit.record(actor_id="sim_owner_alpha",action="rejected_replay",
                          reason="replay",entity_id="sim_evt_incorrect0001")
        self.audit.record(actor_id="sim_owner_alpha",action="rate_limit",
                          reason="count_limit",entity_id="sim_evt_incorrect0002")
        proof=self.audit.verify()
        self.assertTrue(proof.valid,proof.reasons)
        records=self.audit.by_actor("sim_owner_alpha")
        self.assertEqual(len(records),2)
        self.assertNotIn("sim_evt_incorrect0001",str(records))

    def test_outbox_cannot_store_pii(self):
        with self.assertRaises(InvalidValue):
            self.outbox.enqueue(event_id=self.event.event_id,destination="sim_customer_notice",
                                payload={"type":"POSTED","phone":"01700000000"})

    def test_retry_delivery(self):
        msg=self.outbox.enqueue(event_id=self.event.event_id,destination="sim_customer_notice",
                                payload={"type":"POSTED","amount_poisha":10000,"currency":"BDT"})
        self.assertEqual(msg.state,"ready")
        self.assertEqual(self.outbox.enqueue(event_id=self.event.event_id,destination="sim_customer_notice",
                  payload={"type":"POSTED","amount_poisha":10000,"currency":"BDT"}).message_id,msg.message_id)
        with self.assertRaises(Conflict):
            self.outbox.enqueue(event_id=self.event.event_id,destination="sim_customer_notice",
                  payload={"type":"CANCELLED","amount_poisha":10000,"currency":"BDT"})
        lease=self.outbox.lease()[0]
        with self.assertRaises(AuthorizationError):
            self.outbox.ack(message_id=msg.message_id,token="x"*48)
        self.assertEqual(self.outbox.ack(message_id=msg.message_id,token=lease.lease_token).state,"delivered")
        with self.assertRaises(StateError):
            self.outbox.ack(message_id=msg.message_id,token=lease.lease_token)

    def test_account_reconstruction(self):
        r=LedgerAuditor(self.ledger).audit_account("sim_customer_alpha")
        self.assertTrue(r.matches)
        self.assertEqual(r.posted_credits,10000)
        self.assertTrue(LedgerAuditor(self.ledger).audit_all()["audit_passed"])

if __name__=="__main__": unittest.main()
