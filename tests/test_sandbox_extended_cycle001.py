"""Cross-domain fictitious finance cases: no provider or customer account connectivity."""
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path

from app.sandboxfinance.identity import SyntheticRegistry,Party,synthetic_customer,synthetic_agent
from app.sandboxfinance.ledger import SandboxLedger, InsufficientFunds, LedgerError
from app.sandboxfinance.workflows import prepare_synthetic_system
from app.sandboxfinance.gateway import InternalMerchantGateway,GatewayStateError,GatewayAuthError
from app.sandboxfinance.loans import (SyntheticLoanBook,BorrowerEvidence,pilot_credit_policy,
    amortization_schedule,CreditStateError,CreditPolicyDenied)
from app.sandboxfinance.limits import VelocityBook,LimitExceeded,LimitError
from app.sandboxfinance.security import LocalAuth, AuthenticationFailed,AccountLocked
from app.sandboxfinance.agency import AgentLiquidityDesk,AgencyStateError
from app.sandboxfinance.support import SyntheticSupportDesk,SupportStateError,SupportPermissionError,SupportError
from app.sandboxfinance.receipts import ReceiptDesk,ReceiptError
from app.sandboxfinance.reports import SandboxReports,ReportingError
from app.sandboxfinance.scenarios import FinanceScenario


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path=Path(self.tmp.name)/"sandbox_finance.sqlite3"
        self.ledger=SandboxLedger(self.db_path)
        self.registry=SyntheticRegistry()
        for p in (
            synthetic_customer("alice","01711111111","Alice Example"),
            synthetic_customer("bob","01822222222","Bob Example"),
            synthetic_agent("agent","01933333333","Agent Example"),
            Party("sim_merchant","merchant","Merchant Example","01644444444"),
            Party("sim_operator","operator","Operator Example","01555555555"),
        ):
            self.registry.register(p)
            self.registry.approve_sandbox(p.party_id)
        prepare_synthetic_system(self.ledger,self.registry)
        for account,amount,reference in (
            ("sim_wallet_alice",1_000_000,"fund-alice"),
            ("sim_wallet_bob",50_000,"fund-bob"),
            ("sim_platform_treasury",5_000_000,"fund-treasury"),
            ("sim_float_agent",200_000,"fund-agent"),
        ):
            self.ledger.synthetic_issue(account,amount,reference=reference)


class MerchantGatewayTests(Fixture):
    def setUp(self):
        super().setUp()
        self.gateway=InternalMerchantGateway(self.ledger,self.registry)
        self.key="fictional-merchant-key-very-long-000000000001"
        self.gateway.register_merchant("sim_merchant",self.key)

    def _intent(self,ref="invoice-0001",amount=20_000):
        return self.gateway.create_intent(merchant_id="sim_merchant",merchant_key=self.key,
            customer_id="sim_alice",invoice_ref=ref,principal_poisha=amount)

    def test_capture_and_refund_are_balanced(self):
        intent=self._intent()
        self.assertIn("sandbox://",intent.qr_payload)
        self.assertEqual(intent.intent.status,"created")
        completed=self.gateway.capture(intent.intent.intent_id,customer_id="sim_alice",
                                       customer_approval_token=intent.customer_approval_token)
        self.assertEqual(completed.status,"captured")
        self.assertEqual(self.ledger.account("sim_wallet_alice").balance_poisha,980_000)
        self.assertEqual(self.ledger.account("sim_merchant_merchant").balance_poisha,19_910)
        self.assertEqual(self.ledger.account("sim_platform_revenue").balance_poisha,90)
        reversed_=self.gateway.refund_full(intent.intent.intent_id,merchant_id="sim_merchant",
                    merchant_key=self.key,reason="synthetic_customer_refund")
        self.assertEqual(reversed_.status,"refunded")
        self.assertEqual(self.ledger.account("sim_wallet_alice").balance_poisha,1_000_000)
        self.assertEqual(self.ledger.account("sim_platform_revenue").balance_poisha,0)
        self.assertEqual(self.ledger.verify()["net_poisha"],0)
        with self.assertRaises(GatewayStateError):
            self.gateway.refund_full(intent.intent.intent_id,merchant_id="sim_merchant",
                  merchant_key=self.key,reason="duplicate_refund_attempt")
        self.assertEqual(len(self.gateway.event_history(intent.intent.intent_id)),3)

    def test_merchant_wrong_key_and_duplicate_invoice(self):
        with self.assertRaises(GatewayAuthError):
            self.gateway.create_intent(merchant_id="sim_merchant",merchant_key="wrong",
                customer_id="sim_alice",invoice_ref="inv001",principal_poisha=1000)
        self._intent()
        with self.assertRaises(GatewayStateError):
            self._intent()
        self.assertEqual(self.gateway.merchant_summary("sim_merchant",merchant_key=self.key)["states"]["created"]["count"],1)

    def test_capture_requires_customer_consent(self):
        intent=self._intent()
        with self.assertRaises(GatewayAuthError):
            self.gateway.capture(intent.intent.intent_id,customer_id="sim_alice",
                                 customer_approval_token="incorrect")
        with self.assertRaises(GatewayAuthError):
            self.gateway.capture(intent.intent.intent_id,customer_id="sim_bob",
                                 customer_approval_token=intent.customer_approval_token)
        self.assertEqual(self.gateway.get_intent(intent.intent.intent_id).status,"created")

    def test_cancel_locks_unspent_session(self):
        intent=self._intent()
        self.gateway.cancel(intent.intent.intent_id,merchant_id="sim_merchant",merchant_key=self.key)
        with self.assertRaises(GatewayStateError):
            self.gateway.capture(intent.intent.intent_id,customer_id="sim_alice",
                                 customer_approval_token=intent.customer_approval_token)
        self.assertEqual(self.ledger.verify()["events"],4)

    def test_atomic_capture_rollback_if_customer_lacks_balance(self):
        intent=self._intent(ref="large-invoice",amount=1_500_000)
        with self.assertRaises(InsufficientFunds):
            self.gateway.capture(intent.intent.intent_id,customer_id="sim_alice",
                                 customer_approval_token=intent.customer_approval_token)
        self.assertEqual(self.gateway.get_intent(intent.intent.intent_id).status,"created")
        self.assertEqual(self.ledger.verify()["events"],4)


class SyntheticCreditTests(Fixture):
    def setUp(self):
        super().setUp()
        self.loans=SyntheticLoanBook(self.ledger,self.registry)
        self.evidence=BorrowerEvidence("sim_alice",250_000,50_000,0,700)

    def _approved_loan(self):
        case,assessment=self.loans.apply(evidence=self.evidence,principal_poisha=100_000,
                                         term_months=3)
        self.assertTrue(assessment.eligible)
        self.loans.decide(case.application_id,operator_id="sim_operator",approve=True,
                          assessment=assessment,explanation="synthetic_affordability_verified")
        return self.loans.disburse(case.application_id,operator_id="sim_operator")

    def test_plan_reconciles_and_repayment(self):
        case=self._approved_loan()
        installments=self.loans.installment_plan(case.application_id)
        self.assertEqual(sum(r["principal_poisha"] for r in installments),100_000)
        self.assertGreater(sum(r["interest_poisha"] for r in installments),0)
        for installment in installments:
            case=self.loans.pay_next(case.application_id,customer_id="sim_alice")
        self.assertEqual(case.status,"paid_off")
        self.assertEqual(case.remaining_principal_poisha,0)
        self.assertEqual(case.remaining_interest_poisha,0)
        self.assertEqual(self.ledger.verify()["net_poisha"],0)
        with self.assertRaises(CreditStateError):
            self.loans.pay_next(case.application_id,customer_id="sim_alice")

    def test_reject_ineligible_synthetic_borrower(self):
        poor=BorrowerEvidence("sim_alice",20_000,18_000,100_000,100)
        case,assessment=self.loans.apply(evidence=poor,principal_poisha=100_000,term_months=3)
        self.assertFalse(assessment.eligible)
        self.assertTrue(assessment.reason_codes)
        with self.assertRaises(CreditPolicyDenied):
            self.loans.decide(case.application_id,operator_id="sim_operator",approve=True,
                              assessment=assessment,explanation="attempted_invalid_approval")
        self.assertEqual(self.loans.case(case.application_id).status,"applied")

    def test_denied_loan_cannot_disburse(self):
        case,assessment=self.loans.apply(evidence=self.evidence,principal_poisha=100_000,term_months=3)
        self.loans.decide(case.application_id,operator_id="sim_operator",approve=False,
                          assessment=assessment,explanation="synthetic_risk_policy_override")
        with self.assertRaises(CreditStateError):
            self.loans.disburse(case.application_id,operator_id="sim_operator")
        self.assertEqual(self.loans.portfolio()["unlicensed_real_loans"],0)

    def test_interest_schedule_is_exact_poisha(self):
        schedule=amortization_schedule(100_000,6,1200)
        self.assertEqual(sum(x.principal_poisha for x in schedule),100_000)
        self.assertGreater(sum(x.interest_poisha for x in schedule),0)
        self.assertEqual(len(schedule),6)


class VelocityTests(Fixture):
    def setUp(self):
        super().setUp()
        self.limits=VelocityBook(self.ledger._connect)

    def _reserve(self,key,amount):
        with self.ledger._lock,self.ledger._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            result=self.limits.reserve_in_transaction(db,event_ref=key,owner_id="sim_alice",
                counterparty_id="sim_bob",category="transfer",amount_poisha=amount)
            db.commit()
            return result

    def test_accepted_event_and_idempotent_replay(self):
        result=self._reserve("sim-limit-ref-01",10_000)
        self.assertTrue(result.accepted)
        self.assertEqual(self.limits.event_count("sim_alice"),1)
        self.assertTrue(self._reserve("sim-limit-ref-01",10_000).accepted)
        self.assertEqual(self.limits.event_count("sim_alice"),1)
        with self.assertRaises(LimitError):
            self._reserve("sim-limit-ref-01",20_000)

    def test_velocity_limit_rejects_without_recording(self):
        with self.assertRaises(LimitExceeded):
            self._reserve("sim-limit-ref-02",250_000)
        self.assertEqual(self.limits.event_count("sim_alice"),0)

    def test_hourly_count_is_enforced(self):
        for n in range(6):
            self._reserve(f"sim-limit-{n:02d}",1000)
        with self.assertRaises(LimitExceeded):
            self._reserve("sim-limit-over",1000)
        self.assertTrue(self.limits.verify_no_duplicate_references())


class AccountAuthTests(Fixture):
    def setUp(self):
        super().setUp()
        self.auth=LocalAuth(self.ledger,self.registry,max_failures=3,lock_minutes=5)
        self.auth.provision("sim_alice","fictional-local-passphrase",device_label="android-demo-device-001")

    def test_session_scope_and_device_binding(self):
        session=self.auth.authenticate("sim_alice","fictional-local-passphrase",
                     device_label="android-demo-device-001",scopes={"transfer"})
        self.assertEqual(self.auth.authorize(session.bearer_token,
            device_label="android-demo-device-001",scope="transfer").subject_id,"sim_alice")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authorize(session.bearer_token,device_label="wrong-device",scope="transfer")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authorize(session.bearer_token,device_label="android-demo-device-001",scope="view_account")
        self.auth.revoke(session.session.session_ref,subject_id="sim_alice")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authorize(session.bearer_token,device_label="android-demo-device-001",scope="transfer")

    def test_failed_login_eventually_locks_account(self):
        for _ in range(3):
            with self.assertRaises(AuthenticationFailed):
                self.auth.authenticate("sim_alice","wrong",device_label="android-demo-device-001",scopes={"transfer"})
        with self.assertRaises(AccountLocked):
            self.auth.authenticate("sim_alice","fictional-local-passphrase",
                device_label="android-demo-device-001",scopes={"transfer"})
        self.assertEqual(len([x for x in self.auth.audit("sim_alice") if x["event"]=="authentication_failed"]),3)

    def test_rotate_invalidates_all_sessions(self):
        prior=self.auth.authenticate("sim_alice","fictional-local-passphrase",
                device_label="android-demo-device-001",scopes={"view_account"})
        self.auth.rotate_secret("sim_alice",old_secret="fictional-local-passphrase",
                new_secret="new-fictional-passphrase",device_label="android-demo-device-001")
        with self.assertRaises(AuthenticationFailed):
            self.auth.authorize(prior.bearer_token,device_label="android-demo-device-001",scope="view_account")
        updated=self.auth.authenticate("sim_alice","new-fictional-passphrase",
                device_label="android-demo-device-001",scopes={"view_account"})
        self.assertTrue(updated.session.synthetic)


class AgentSupportReportsTests(Fixture):
    def test_agent_float_replenishment_has_operator_approval(self):
        desk=AgentLiquidityDesk(self.ledger,self.registry)
        req=desk.request_float("sim_agent",150_000,reason="forecast_float_shortage")
        result=desk.decide(req.request_id,operator_id="sim_operator",approve=True,
                           reason="approved_fictional_float")
        self.assertEqual(result.state,"approved")
        self.assertEqual(self.ledger.account("sim_float_agent").balance_poisha,350_000)
        self.assertEqual(self.ledger.verify()["net_poisha"],0)
        with self.assertRaises(AgencyStateError):
            desk.decide(req.request_id,operator_id="sim_operator",approve=True,
                        reason="duplicate_replenish")

    def test_agent_can_cancel_pending_request(self):
        desk=AgentLiquidityDesk(self.ledger,self.registry)
        req=desk.request_float("sim_agent",100_000,reason="test_float_scenario")
        self.assertEqual(desk.cancel(req.request_id,agent_id="sim_agent").state,"cancelled")
        self.assertEqual(desk.agent_float_position("sim_agent")["pending_synthetic_replenishment_poisha"],0)

    def test_helpdesk_is_distinct_from_financial_movement(self):
        desk=SyntheticSupportDesk(self.ledger,self.registry)
        before=self.ledger.verify()["events"]
        ticket=desk.open(reporter_id="sim_alice",category="cash_handover",priority="high",
            related_reference="sim_reference-012",description_code="test_cash_difference")
        desk.assign(ticket.ticket_id,operator_id="sim_operator")
        digest=hashlib.sha256(b"fictional-support-evidence").hexdigest()
        desk.add_evidence(ticket.ticket_id,actor_id="sim_alice",
                          evidence_digest=digest,evidence_type="simulation_log")
        desk.transition(ticket.ticket_id,operator_id="sim_operator",to_state="triage",
                        reason_code="synthetic_case_review")
        resolved=desk.transition(ticket.ticket_id,operator_id="sim_operator",to_state="resolved",
                 reason_code="synthetic_claim_closed",resolution_digest=digest)
        self.assertEqual(resolved.status,"resolved")
        desk.transition(ticket.ticket_id,operator_id="sim_operator",to_state="closed",
                        reason_code="close_after_resolution")
        with self.assertRaises(SupportStateError):
            desk.transition(ticket.ticket_id,operator_id="sim_operator",to_state="triage",
                            reason_code="cannot_reopen_closed")
        self.assertEqual(self.ledger.verify()["events"],before)
        self.assertEqual(desk.evidence_digests(ticket.ticket_id),(digest,))

    def test_fictional_receipt_bilingual_and_signed(self):
        receipt=self.ledger.transfer("sim_wallet_alice","sim_wallet_bob",1200,
                                      reference="test-receipt-01")
        desk=ReceiptDesk(self.ledger)
        evidence=desk.create(receipt.event_id,owner_account="sim_wallet_alice")
        self.assertIn("FICTIONAL",desk.render_text(evidence,language="en"))
        self.assertIn("কাল্পনিক",desk.render_text(evidence,language="bn"))
        self.assertTrue(desk.verify_against_journal(evidence))
        signed=desk.sign_local_copy(evidence,test_secret="sandbox-receipt-key-11111111111111111")
        self.assertTrue(desk.verify_local_copy(signed,test_secret="sandbox-receipt-key-11111111111111111"))
        signed["receipt"]["amount_bdt"]="9999.00"
        self.assertFalse(desk.verify_local_copy(signed,test_secret="sandbox-receipt-key-11111111111111111"))
        with self.assertRaises(ReceiptError):
            desk.create(receipt.event_id,owner_account="sim_platform_treasury")

    def test_reporting_is_read_only_and_synthetic(self):
        report=SandboxReports(self.ledger)
        before=self.ledger.verify()["events"]
        snapshot=report.compact_snapshot()
        self.assertTrue(snapshot["simulation"])
        self.assertFalse(snapshot["bank_settlements_confirmed"])
        self.assertIn("simulation,operation",report.export_operation_csv())
        stressed=report.stress_scenario(cashout_volume=50,average_cashout_poisha=100_000,
                 cashin_volume=30,average_cashin_poisha=100_000,expected_loss_poisha=50_000)
        self.assertFalse(stressed["commercially_viable_proven"])
        self.assertEqual(self.ledger.verify()["events"],before)

    def test_full_simulation_has_balanced_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=FinanceScenario(Path(directory)/"scenario.sqlite3")
            result=scenario.execute()
            self.assertTrue(result.invariant_balanced)
            self.assertEqual(result.actual_money_moved_poisha,0)
            self.assertFalse(scenario.snapshot()["bank_settlements_confirmed"])
            self.assertGreater(result.posted_events,0)


if __name__=="__main__":
    unittest.main()
