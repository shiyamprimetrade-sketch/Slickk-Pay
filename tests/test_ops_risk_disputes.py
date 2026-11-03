"""Conservative provider-risk triage and human-only dispute workflow tests."""
import unittest
from datetime import datetime, timezone, timedelta

from app.ops.risk import RiskEvaluator, RiskInput, RiskPolicy, Decision
from app.ops.disputes import (
    DisputeDesk, EvidenceItem, CaseType, CaseState, Severity,
)
from app.ops.primitives import EvidenceError, PolicyError, ConflictError, NotFoundError

T=datetime(2026,11,3,12,0,tzinfo=timezone.utc)


def risk_item(transaction="tx-1",order="ord-1", *, amount=10000,
              verified=True, risk_level=0, invoice=True, merchant="merchant-A",
              created_at=T, change_count=0, chargebacks=0):
    return RiskInput(merchant,order,transaction,amount,created_at,"BDT",verified,
                     risk_level,1,invoice,chargebacks,change_count)


def policy(**kw):
    return RiskPolicy("merchant-A",version=1,**kw)


def evidence(eid="evidence-1", verified_by="reviewer-A"):
    return EvidenceItem(eid,"provider_letter","a"*64,verified_by,T)


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.evaluator=RiskEvaluator()

    def assess(self,item=None,pol=None,*,record=False):
        return self.evaluator.evaluate(item or risk_item(),pol or policy(),
                                       now=T,record=record)

    def test_low_risk_is_only_allowed_to_validate(self):
        result=self.assess()
        self.assertEqual(result.decision,Decision.ALLOW_TO_VALIDATE)
        self.assertFalse(result.as_dict()["authorizes_payment_or_settlement"])
        self.assertEqual(result.score,0)

    def test_missing_provider_validation_is_held(self):
        result=self.assess(risk_item(verified=False,risk_level=None))
        self.assertEqual(result.decision,Decision.HOLD_MISSING_EVIDENCE)
        self.assertIn("provider_verification_missing",result.reasons)

    def test_gateway_high_risk_is_always_held(self):
        result=self.assess(risk_item(risk_level=1))
        self.assertEqual(result.decision,Decision.HOLD_PROVIDER_RISK)
        self.assertIn("provider_risk_hold",result.reasons)

    def test_invoices_must_be_verified(self):
        result=self.assess(risk_item(invoice=False))
        self.assertIn("merchant_invoice_unverified",result.reasons)
        self.assertEqual(result.decision,Decision.REVIEW)

    def test_large_amount_rule(self):
        result=self.assess(risk_item(amount=6000000))
        self.assertIn("large_amount",result.reasons)
        self.assertEqual(result.score,25)

    def test_chargeback_history_rules(self):
        result=self.assess(risk_item(chargebacks=3))
        self.assertIn("previous_disputes",result.reasons)
        self.assertGreaterEqual(result.score,60)

    def test_merchant_policy_scoping(self):
        with self.assertRaises(PolicyError):
            self.assess(risk_item(merchant="merchant-B"))

    def test_policy_version_drift(self):
        with self.assertRaises(PolicyError):
            self.assess(risk_item(),RiskPolicy("merchant-A",version=2))

    def test_recorded_same_transaction_is_idempotent(self):
        first=self.assess(record=True)
        second=self.assess(record=True)
        self.assertEqual(first,second)
        self.assertEqual(self.evaluator.count("merchant-A"),1)

    def test_recorded_transaction_cannot_be_rewritten(self):
        self.assess(record=True)
        with self.assertRaises(ConflictError):
            self.assess(risk_item(amount=11000),record=True)

    def test_reused_order_detected(self):
        self.assess(record=True)
        second=self.assess(risk_item("tx-2","ord-1"))
        self.assertEqual(second.decision,Decision.REJECT_DUPLICATE)
        self.assertIn("reused_order_reference",second.reasons)

    def test_event_velocity_limit(self):
        self.assess(record=True)
        strict=policy(maximum_events_per_window=1)
        second=self.assess(risk_item("tx-2","ord-2"),strict)
        self.assertIn("high_event_velocity",second.reasons)
        self.assertEqual(second.decision,Decision.REVIEW)

    def test_amount_velocity_limit(self):
        self.assess(record=True)
        strict=policy(maximum_window_amount_poisha=15000)
        second=self.assess(risk_item("tx-2","ord-2"),strict)
        self.assertIn("high_amount_velocity",second.reasons)

    def test_preview_is_not_recorded(self):
        self.assess(record=False)
        self.assertEqual(self.evaluator.count("merchant-A"),0)
        self.assertEqual(self.evaluator.merchant_summary("merchant-A")["recorded"],0)

    def test_future_event_rejected(self):
        with self.assertRaises(EvidenceError):
            self.assess(risk_item(created_at=T+timedelta(seconds=5)))

    def test_merchant_summary(self):
        self.assess(record=True)
        self.assertEqual(self.evaluator.merchant_summary("merchant-A")["hold_count"],0)
        self.assertFalse(self.evaluator.merchant_summary("merchant-A")["payment_authorization_possible"])


class DisputeDeskTests(unittest.TestCase):
    def setUp(self):
        self.desk=DisputeDesk()
        self.case=self.desk.open(case_id="case-A",merchant_id="merchant-A",payment_ref="pay-A",
            case_type=CaseType.PROVIDER_DISCREPANCY,severity=Severity.HIGH,
            actor="reviewer-A",opened_at=T)

    def transition(self,new_state,event_ref,at=T):
        return self.desk.transition(merchant_id="merchant-A",case_id="case-A",
                                    to_state=new_state,event_ref=event_ref,
                                    actor="reviewer-A",occurred_at=at)

    def test_open_case_metadata_and_audit(self):
        self.assertEqual(self.case.state,CaseState.OPEN)
        self.assertEqual(len(self.case.events),1)
        self.assertTrue(self.desk.verify_audit(merchant_id="merchant-A",case_id="case-A"))

    def test_valid_triage_and_waiting_state(self):
        self.transition(CaseState.TRIAGE,"event-A",T+timedelta(minutes=1))
        item=self.transition(CaseState.WAITING_PROVIDER,"event-B",T+timedelta(minutes=2))
        self.assertEqual(item.state,CaseState.WAITING_PROVIDER)
        self.assertTrue(self.desk.verify_audit(merchant_id="merchant-A",case_id="case-A"))

    def test_close_without_resolution_is_rejected(self):
        with self.assertRaises(PolicyError):
            self.transition(CaseState.CLOSED,"event-A")

    def test_resolution_requires_evidence(self):
        self.transition(CaseState.TRIAGE,"event-A",T+timedelta(minutes=1))
        self.transition(CaseState.EVIDENCE_COMPLETE,"event-B",T+timedelta(minutes=2))
        with self.assertRaises(PolicyError):
            self.transition(CaseState.RESOLVED,"event-C",T+timedelta(minutes=3))

    def test_evidence_review_resolution_and_close(self):
        self.transition(CaseState.TRIAGE,"event-A",T+timedelta(minutes=1))
        self.desk.attach(merchant_id="merchant-A",case_id="case-A",item=evidence(),
            event_ref="attach-1",actor="reviewer-A",occurred_at=T+timedelta(minutes=2))
        self.transition(CaseState.EVIDENCE_COMPLETE,"event-B",T+timedelta(minutes=3))
        self.transition(CaseState.RESOLVED,"event-C",T+timedelta(minutes=4))
        closed=self.transition(CaseState.CLOSED,"event-D",T+timedelta(minutes=5))
        self.assertEqual(closed.state,CaseState.CLOSED)
        self.assertTrue(self.desk.verify_audit(merchant_id="merchant-A",case_id="case-A"))

    def test_rejected_case_also_requires_evidence(self):
        with self.assertRaises(PolicyError):
            self.transition(CaseState.REJECTED,"event-A")

    def test_case_assignment_is_audited(self):
        record=self.desk.assign(merchant_id="merchant-A",case_id="case-A",
            assignee="operator-17",event_ref="assignment-1",actor="reviewer-A",occurred_at=T)
        self.assertEqual(record.assigned_to,"operator-17")
        self.assertEqual(len(record.events),2)

    def test_duplicate_evidence_blocked(self):
        self.desk.attach(merchant_id="merchant-A",case_id="case-A",item=evidence(),
            event_ref="attach-1",actor="reviewer-A",occurred_at=T)
        with self.assertRaises(ConflictError):
            self.desk.attach(merchant_id="merchant-A",case_id="case-A",item=evidence(),
                event_ref="attach-2",actor="reviewer-A",occurred_at=T)

    def test_event_reference_cannot_be_reused(self):
        self.transition(CaseState.TRIAGE,"event-A")
        with self.assertRaises(ConflictError):
            self.transition(CaseState.WAITING_PROVIDER,"event-A")

    def test_dispute_isolation(self):
        with self.assertRaises(NotFoundError):
            self.desk.get("case-A",merchant_id="merchant-B")
        self.assertEqual(self.desk.list_cases(merchant_id="merchant-B",now=T),())

    def test_overdue_is_based_on_deadline(self):
        self.assertFalse(self.case.overdue(T+timedelta(hours=24)))
        self.assertTrue(self.case.overdue(T+timedelta(hours=49)))

    def test_negative_time_travel_rejected(self):
        with self.assertRaises(EvidenceError):
            self.transition(CaseState.TRIAGE,"event-back",T-timedelta(seconds=1))

    def test_public_case_summary_has_no_pii(self):
        data=self.case.summary(now=T)
        self.assertFalse(data["refund_or_dispute_executed"])
        self.assertEqual(data["evidence_count"],0)
        self.assertNotIn("customer_email",data)

    def test_case_dashboard_and_overdue_count(self):
        data=self.desk.dashboard(merchant_id="merchant-A",now=T+timedelta(hours=100))
        self.assertEqual(data["case_count"],1)
        self.assertEqual(data["overdue_count"],1)
        self.assertFalse(data["refund_automation_enabled"])

    def test_duplicate_case_reference_fails(self):
        with self.assertRaises(ConflictError):
            self.desk.open(case_id="case-A",merchant_id="merchant-A",payment_ref="pay-B",
                case_type=CaseType.OTHER,severity=Severity.LOW,actor="reviewer-A",opened_at=T)

    def test_evidence_digest_validation(self):
        with self.assertRaises(EvidenceError):
            EvidenceItem("id","provider_letter","short","reviewer",T)


if __name__=="__main__":
    unittest.main()
