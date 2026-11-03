"""Shadow journal accounting tests: atomicity, reversals and tamper evidence."""
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import replace

from app.ops.journal import (
    ShadowJournal, Account, AccountClass, Side, Posting,
)
from app.ops.primitives import ConflictError, EvidenceError, PolicyError, InvariantError

T=datetime(2026,11,3,12,0,tzinfo=timezone.utc)


class ShadowJournalTests(unittest.TestCase):
    def setUp(self):
        self.j=ShadowJournal()
        self.j.add_account(Account("gateway-clearing","merchant-A",AccountClass.CLEARING_ASSET))
        self.j.add_account(Account("merchant-payable","merchant-A",AccountClass.MERCHANT_PAYABLE))
        self.j.add_account(Account("gateway-fees","merchant-A",AccountClass.GATEWAY_FEES))
        self.j.add_account(Account("other-merchant","merchant-B",AccountClass.MERCHANT_PAYABLE))

    def postings(self, amount=10000):
        return [Posting("gateway-clearing",Side.DEBIT,amount),
                Posting("merchant-payable",Side.CREDIT,amount)]

    def append(self, eid="entry-1", ref="provider-A",amount=10000):
        return self.j.append(entry_id=eid,merchant_id="merchant-A",event_ref=ref,
                             event_kind="provider_evidence",occurred_at=T,
                             postings=self.postings(amount))

    def test_balanced_entry_and_trial_balance(self):
        entry=self.append()
        self.assertEqual(entry.total_debit_poisha,10000)
        self.assertEqual(entry.total_credit_poisha,10000)
        self.assertTrue(entry.verify_hash())
        report=self.j.trial_balance("merchant-A")
        self.assertEqual(report["total_debits_bdt"],"100.00")
        self.assertEqual(report["total_credits_bdt"],"100.00")

    def test_chain_is_deterministic_and_verifiable(self):
        first=self.append()
        second=self.append("entry-2","provider-B",5000)
        self.assertEqual(first.sequence,1)
        self.assertEqual(second.sequence,2)
        self.assertEqual(second.prior_hash,first.entry_hash)
        self.assertTrue(self.j.verify_chain())
        self.assertEqual(self.j.chain_root(),second.entry_hash)

    def test_entry_idempotency(self):
        first=self.append()
        again=self.append()
        self.assertIs(first,again)
        self.assertEqual(self.j.stats()["entry_count"],1)

    def test_conflicting_event_is_rejected(self):
        self.append()
        with self.assertRaises(ConflictError):
            self.append(eid="entry-2",ref="provider-A")
        with self.assertRaises(ConflictError):
            self.append(eid="entry-1",ref="provider-B")

    def test_unbalanced_entry_does_not_mutate(self):
        with self.assertRaises(InvariantError):
            self.j.append(entry_id="unbalanced",merchant_id="merchant-A",
                event_ref="broken",event_kind="provider_evidence",occurred_at=T,
                postings=[Posting("gateway-clearing",Side.DEBIT,100),
                          Posting("merchant-payable",Side.CREDIT,101)])
        self.assertEqual(self.j.stats()["entry_count"],0)

    def test_cross_merchant_posting_rejected(self):
        with self.assertRaises(PolicyError):
            self.j.append(entry_id="cross",merchant_id="merchant-A",
                event_ref="cross",event_kind="provider_evidence",occurred_at=T,
                postings=[Posting("gateway-clearing",Side.DEBIT,100),
                          Posting("other-merchant",Side.CREDIT,100)])

    def test_unknown_account_rejected(self):
        with self.assertRaises(EvidenceError):
            self.j.append(entry_id="unknown",merchant_id="merchant-A",
                event_ref="unknown",event_kind="provider_evidence",occurred_at=T,
                postings=[Posting("missing",Side.DEBIT,100),
                          Posting("merchant-payable",Side.CREDIT,100)])

    def test_reversal_negates_balances(self):
        entry=self.append()
        reversal=self.j.reverse("entry-1",reversal_id="reversal-1",
                                reversal_event_ref="correct-1",occurred_at=T+timedelta(hours=1))
        self.assertEqual(reversal.reverses_entry,entry.entry_id)
        self.assertEqual(self.j.balance("gateway-clearing").net_debit_poisha,0)
        self.assertEqual(self.j.balance("merchant-payable").net_debit_poisha,0)
        self.assertTrue(self.j.verify_chain())

    def test_multiple_reversals_rejected(self):
        self.append()
        self.j.reverse("entry-1",reversal_id="rev-1",reversal_event_ref="rev-event-1",occurred_at=T)
        with self.assertRaises(ConflictError):
            self.j.reverse("entry-1",reversal_id="rev-2",reversal_event_ref="rev-event-2",occurred_at=T)

    def test_reverse_reversal_rejected(self):
        self.append()
        self.j.reverse("entry-1",reversal_id="rev-1",reversal_event_ref="rev-event-1",occurred_at=T)
        with self.assertRaises(PolicyError):
            self.j.reverse("rev-1",reversal_id="rev-2",reversal_event_ref="rev-event-2",occurred_at=T)

    def test_merchant_isolation_in_entries(self):
        self.append()
        self.assertEqual(len(self.j.entries("merchant-A")),1)
        self.assertEqual(len(self.j.entries("merchant-B")),0)
        with self.assertRaises(EvidenceError):
            self.j.entry("entry-1",merchant_id="merchant-B")

    def test_an_account_cannot_change_definition(self):
        self.j.add_account(Account("gateway-clearing","merchant-A",AccountClass.CLEARING_ASSET))
        with self.assertRaises(ConflictError):
            self.j.add_account(Account("gateway-clearing","merchant-A",AccountClass.SETTLEMENT_ASSET))

    def test_tampered_chain_is_detected(self):
        self.append()
        self.j._entries[0]=replace(self.j._entries[0],entry_hash="0"*64)
        self.assertFalse(self.j.verify_chain())
        with self.assertRaises(InvariantError):
            self.j.chain_root()

    def test_empty_journal_genesis(self):
        self.assertEqual(ShadowJournal().chain_root(),"0"*64)
        self.assertTrue(ShadowJournal().verify_chain())

    def test_invalid_posting_values(self):
        with self.assertRaises(EvidenceError):
            Posting("gateway-clearing",Side.DEBIT,0)
        with self.assertRaises(EvidenceError):
            Posting("gateway-clearing","debit",100)

    def test_inactive_account_disallowed(self):
        self.j.add_account(Account("frozen","merchant-A",AccountClass.SUSPENSE_LIABILITY,active=False))
        with self.assertRaises(PolicyError):
            self.j.append(entry_id="frozen-1",merchant_id="merchant-A",
                event_ref="frozen-event",event_kind="provider_evidence",occurred_at=T,
                postings=[Posting("gateway-clearing",Side.DEBIT,100),
                          Posting("frozen",Side.CREDIT,100)])


if __name__=="__main__":
    unittest.main()
