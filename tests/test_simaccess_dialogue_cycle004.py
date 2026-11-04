"""Two independently authenticated review acknowledgements, never cash release."""
import sqlite3
import unittest
from app.simaccess.errors import LabError
from tests.test_simaccess_core_cycle004 import LocalFixture,A,B,AGENT,MERCHANT


class TwoPartyReviewTests(LocalFixture):
    def setUp(self):
        super().setUp()
        quote=self.quote("cash_out",counterpart=AGENT,ref="cashout_dialogue_001")
        self.request=self.lab.requests.review(self.ctx(A),quote.id,explicit_preview_consent=True)

    def test_two_people_may_review_but_not_pay(self):
        self.ctx(AGENT)  # Ensure lazy test login is outside the measured review events.
        before=self.lab.audit.verify().checked
        first=self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="customer_ack_ref0001")
        self.assertTrue(first.customer_reviewed)
        self.assertFalse(first.agent_reviewed)
        second=self.lab.cash_dialogue.acknowledge(self.ctx(AGENT),self.request.id,review_reference="agent_ack_ref0000001")
        self.assertEqual(second.state,"both_reviewed")
        self.assertFalse(second.cash_handover_authorized)
        self.assertFalse(second.public()["ledger_posting"])
        self.assertEqual(self.lab.audit.verify().checked,before+2)
        with self.assertRaises(LabError) as err:
            self.lab.cash_dialogue.real_handover(self.ctx(AGENT),self.request.id)
        self.assertEqual(err.exception.code,"SERVER_AUTHORITY_ABSENT")

    def test_wrong_customer_cannot_acknowledge(self):
        with self.assertRaises(LabError) as err:
            self.lab.cash_dialogue.acknowledge(self.ctx(B),self.request.id,review_reference="wrong_person_ref_01")
        self.assertEqual(err.exception.code,"ROLE_FORBIDDEN")

    def test_wrong_merchant_cannot_acknowledge(self):
        with self.assertRaises(LabError):
            self.lab.cash_dialogue.acknowledge(self.ctx(MERCHANT),self.request.id,review_reference="merchant_ref_00001")

    def test_reference_idempotent_same_actor(self):
        first=self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="replay_same_owner_001")
        second=self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="replay_same_owner_001")
        self.assertEqual(first.public(),second.public())

    def test_conflicting_reference_blocked(self):
        self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="owner_review_00001")
        with self.assertRaises(LabError) as err:
            self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="owner_review_00002")
        self.assertEqual(err.exception.code,"REPLAY_BLOCKED")

    def test_same_reference_cannot_be_used_by_both_roles(self):
        self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="identical_ref_00001")
        with self.assertRaises(LabError):
            self.lab.cash_dialogue.acknowledge(self.ctx(AGENT),self.request.id,review_reference="identical_ref_00001")

    def test_customer_may_cancel_and_never_reactivate(self):
        self.lab.cash_dialogue.start(self.ctx(A),self.request.id)
        self.assertEqual(self.lab.cash_dialogue.cancel(self.ctx(A),self.request.id).state,"cancelled")
        with self.assertRaises(LabError):
            self.lab.cash_dialogue.acknowledge(self.ctx(AGENT),self.request.id,review_reference="after_cancel_ref0001")

    def test_expired_request_blocks_repeated_agent_acknowledgement(self):
        self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="before_expiry_ref01")
        self.clock.advance(181)
        with self.assertRaises(LabError):
            self.lab.cash_dialogue.acknowledge(self.ctx(AGENT),self.request.id,review_reference="after_expiry_ref_001")

    def test_negative_handover_constraint(self):
        self.lab.cash_dialogue.start(self.ctx(A),self.request.id)
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store.transaction() as db:
                db.execute("UPDATE lab_cash_ack SET handover_authorized=1 WHERE request_id=?",(self.request.id,))

    def test_cash_in_requires_agent_and_customer_reviewers(self):
        quote=self.quote("cash_in",owner=AGENT,counterpart=B,ref="cashin_dialogue_002")
        review=self.lab.requests.review(self.ctx(AGENT),quote.id,explicit_preview_consent=True)
        a=self.lab.cash_dialogue.start(self.ctx(AGENT),review.id)
        self.assertEqual(a.customer_id,B)
        self.assertEqual(a.agent_id,AGENT)
        result=self.lab.cash_dialogue.acknowledge(self.ctx(B),review.id,review_reference="cashin_customer_ack01")
        self.assertFalse(result.cash_handover_authorized)
        self.assertEqual(result.state,"waiting")

    def test_unrelated_request_ref_replay_blocked(self):
        self.lab.cash_dialogue.acknowledge(self.ctx(A),self.request.id,review_reference="shared_ack_ref00001")
        quote=self.quote("cash_out",counterpart=AGENT,ref="cashout_dialogue_003")
        request=self.lab.requests.review(self.ctx(A),quote.id,explicit_preview_consent=True)
        with self.assertRaises(LabError):
            self.lab.cash_dialogue.acknowledge(self.ctx(A),request.id,review_reference="shared_ack_ref00001")


if __name__=="__main__":
    unittest.main()
