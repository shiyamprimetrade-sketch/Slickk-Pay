"""Security, network, privacy, crash-recovery and integration regression tests."""
import sqlite3
from unittest.mock import patch
import unittest
from fastapi.testclient import TestClient
from app.simaccess.errors import LabError
from app.simaccess.service import AccessLab
from app.simaccess.api import create_local_access_app
from app.simaccess.conformance import ConformanceSuite
from app.simaccess.consistency import ConsistencyAuditor
from app.simaccess.search import ActivitySearch,ActivityQuery
from app.simaccess.faults import FaultProbe
from app.simaccess.offline import OfflineContract,NetworkState
from app.simaccess.risk import SyntheticRiskEngine
from app.simaccess.device_policy import DevicePolicy,DeviceSignals
from app.simaccess.privacy import PrivacyInspector
from app.simaccess.contract import ResponseContract
from app.simaccess.versioning import ContractVersionRegistry,ClientHello
from app.simaccess.directory import AgentDirectory,default_sample_agents
from app.simaccess.disclosures import DisclosureService
from app.simaccess.recovery import LabRecovery
from app.simaccess.store import LabStore
from tests.test_simaccess_core_cycle004 import LocalFixture,A,B,AGENT,MERCHANT,OP,PIN,DEV_A,DEV_B,AT


class SecurityBoundaryTests(LocalFixture):
    def test_audit_integrity_proof(self):
        self.assertTrue(self.lab.audit.verify().valid)
        self.assertGreater(self.lab.audit.verify().checked,0)

    def test_audit_is_append_only(self):
        with self.assertRaises(sqlite3.DatabaseError):
            with self.store.transaction() as db:
                db.execute("DELETE FROM lab_audit WHERE sequence=1")
        self.assertTrue(self.lab.audit.verify().valid)

    def test_audit_write_rollback(self):
        proof=FaultProbe(self.store).assert_rollback(actor_id=A,correlation="fault_probe_0001")
        self.assertTrue(proof.data_unchanged)
        self.assertTrue(proof.injected_error_seen)

    def test_no_posting_tables(self):
        self.assertTrue(self.lab.recovery.assert_no_financial_posting())
        self.assertFalse(self.lab.capabilities.can_move_money)

    def test_conformance_report_passes(self):
        report=ConformanceSuite(self.lab).run()
        self.assertTrue(report.passed,[x.name for x in report.checks if not x.passed])
        self.assertFalse(report.production_ready)

    def test_consistency_report_passes_with_quote(self):
        self.quote()
        self.assertTrue(ConsistencyAuditor(self.store).examine().valid)

    def test_privacy_catches_private_fields(self):
        report=PrivacyInspector().inspect({"actor":"sim_customer_alpha","token":"real-token-should-never-leak"})
        self.assertFalse(report.safe)
        self.assertEqual(report.issues[0].reason,"PRIVATE_FIELD")

    def test_contract_catches_forged_settlement(self):
        result=ResponseContract().validate("receipt",{"simulation":True,"payment_proof":True,"bank_settlement_proof":True})
        self.assertFalse(result.valid)

    def test_contract_validates_quote(self):
        quote=self.quote().public()
        self.assertTrue(ResponseContract().validate("quote",quote).valid)

    def test_agent_directory_has_no_real_business_location(self):
        result=self.lab.directory.search(self.ctx(A),region="dhaka_demo")
        self.assertEqual(len(result["items"]),1)
        self.assertFalse(result["items"][0]["real_cash_available"] if "real_cash_available" in result["items"][0] else False)

    def test_accessible_disclosure_is_simulation(self):
        r=DisclosureService().for_amount("cash_out",30000,"bn")
        self.assertTrue(r.simulation)
        self.assertFalse(r.tax_verified)

    def test_risk_engine_cannot_grant_credit(self):
        item=self.quote("cash_out",counterpart=AGENT,ref="pilot_cashout_risk01")
        report=SyntheticRiskEngine().assess(self.ctx(A),item,quotes_last_hour=9)
        self.assertTrue(report.requires_manual_review)
        self.assertFalse(report.automated_payment_authorization)

    def test_no_offline_payment_policy(self):
        state=NetworkState(online=False,session_valid=True,ui_in_foreground=True,last_verified_at=AT,
                           now=AT+10,clock_trusted=True,consent_banner_seen=True)
        decision=OfflineContract().evaluate("money_send",state)
        self.assertFalse(decision.allowed)
        self.assertFalse(decision.may_mutate_balance)

    def test_offline_allows_only_recent_demo_cache(self):
        state=NetworkState(online=False,session_valid=True,ui_in_foreground=True,last_verified_at=AT,
                           now=AT+10,clock_trusted=True,consent_banner_seen=True)
        self.assertTrue(OfflineContract().evaluate("sample_receipt",state).allowed)
        self.assertFalse(OfflineContract(cached_data_max_age=3).evaluate("sample_receipt",state).allowed)

    def test_device_policy_blocks_payment_even_with_sandbox_consent(self):
        signals=DeviceSignals(True,True,True,True,True,False,False,True,True)
        result=DevicePolicy().evaluate(signals,self.ctx(A))
        self.assertTrue(result.can_review_synthetic_quote)
        self.assertFalse(result.can_authorize_real_money)

    def test_unsigned_preview_not_qr(self):
        with self.assertRaises(LabError):
            self.lab.qr.inspect(self.ctx(A),"https://real-merchant.example/pay/123")

    def test_qr_replay_is_blocked(self):
        qr=self.lab.qr.issue(self.ctx(A),recipient_id=B,operation="transfer",amount_poisha=10000)
        result=self.lab.qr.consume_preview(self.ctx(B),qr)
        self.assertFalse(result.payment_authorized)
        with self.assertRaises(LabError) as err:
            self.lab.qr.consume_preview(self.ctx(B),qr)
        self.assertEqual(err.exception.code,"REPLAY_BLOCKED")

    def test_expired_qr_is_rejected(self):
        uri=self.lab.qr.issue(self.ctx(A),recipient_id=B,operation="transfer",amount_poisha=1000,lifetime=30)
        self.clock.advance(31)
        with self.assertRaises(LabError):
            self.lab.qr.inspect(self.ctx(B),uri)

    def test_support_sanitizes_fake_account_number(self):
        case=self.lab.support.create_draft(self.ctx(A),category="question",
                                            description="I saw test reference 123456789012 and need a sample review")
        self.assertIn("[REDACTED]",case.description)
        self.assertNotIn("123456789012",case.description)

    def test_support_access_scoped(self):
        case=self.lab.support.create_draft(self.ctx(A),category="privacy",description="Sample privacy question for review")
        self.assertEqual(len(self.lab.support.list(self.ctx(B))),0)
        self.assertEqual(self.lab.support.close(self.ctx(A),case.id).status,"closed")

    def test_outbox_only_local(self):
        notice=self.lab.notifications.enqueue(actor_id=A,kind="quote_ready",safe_message="Your sample quote is ready")
        self.assertFalse(notice.delivery_enabled)
        self.assertEqual(len(self.lab.notifications.list_for(self.ctx(B))),0)
        with self.assertRaises(LabError):
            self.lab.notifications.send_to_external_provider(notice)

    def test_outbox_idempotent_and_conflict(self):
        ref="sim_delivery_repeat001"
        a=self.lab.notifications.enqueue(actor_id=A,kind="quote_ready",safe_message="Sample quote ready",event_id=ref)
        b=self.lab.notifications.enqueue(actor_id=A,kind="quote_ready",safe_message="Sample quote ready",event_id=ref)
        self.assertEqual(a.id,b.id)
        with self.assertRaises(LabError):
            self.lab.notifications.enqueue(actor_id=A,kind="quote_ready",safe_message="Different message",event_id=ref)

    def test_recovery_expires_quote_without_money(self):
        q=self.quote()
        self.clock.advance(181)
        result=self.lab.recovery.run_once()
        self.assertEqual(result.quotes_expired,1)
        self.assertTrue(result.audit_valid)
        self.assertEqual(self.lab.quotes.get(self.ctx(A),q.id).status,"expired")

    def test_sample_activity_pagination(self):
        for i in range(4):
            self.lab.identity.add_sample_activity(A,direction="in",amount_poisha=100+i,
                                                  description="sample activity")
        first=ActivitySearch(self.store).execute(self.ctx(A),ActivityQuery(page_size=2))
        self.assertEqual(len(first.rows),2)
        self.assertIsNotNone(first.next_cursor)
        second=ActivitySearch(self.store).execute(self.ctx(A),ActivityQuery(page_size=2,
            before_timestamp=first.next_cursor[0],before_id=first.next_cursor[1]))
        self.assertEqual(len(second.rows),2)

    def test_operator_metrics_are_synthetic(self):
        result=self.lab.reports.synthetic_kpi(self.ctx(OP))
        self.assertEqual(result["real_revenue_poisha"],0)
        with self.assertRaises(LabError):
            self.lab.reports.synthetic_kpi(self.ctx(A))

    def test_version_negotiation_rejects_live_requirements(self):
        registry=ContractVersionRegistry()
        result=registry.negotiate(ClientHello("android_lab_004","lab-v4",1,True,expects_real_bank=True))
        self.assertFalse(result.accepted)
        self.assertFalse(result.can_transact)

    def test_version_negotiation_accepts_readonly_lab(self):
        registry=ContractVersionRegistry()
        result=registry.negotiate(ClientHello("python_lab_004","lab-v4",1,True))
        self.assertTrue(result.accepted)
        self.assertFalse(result.can_transact)

    def test_agent_checklist_does_not_handover(self):
        quote=self.quote("cash_out",counterpart=AGENT,ref="cash_review_agent_0001")
        request=self.lab.requests.review(self.ctx(A),quote.id,explicit_preview_consent=True)
        check=self.lab.cash.create(self.ctx(AGENT),request_id=request.id)
        self.assertFalse(check.handover_authorized)
        updated=self.lab.cash.update(self.ctx(AGENT),request_id=request.id,cash_available=True,
                                     customer_present=True,warnings_acknowledged=True)
        self.assertFalse(updated.public()["handover_authorized"])
        with self.assertRaises(LabError):
            self.lab.cash.handover(self.ctx(AGENT),request.id)


class ApiBoundaryTests(LocalFixture):
    def setUp(self):
        super().setUp()
        self.app=create_local_access_app(self.lab,explicitly_opted_in=True)
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_health_never_advertises_money(self):
        data=self.client.get("/lab/v4/health").json()
        self.assertFalse(data["posting_enabled"])
        self.assertTrue(data["simulation"])

    def test_login_requires_correct_device(self):
        r=self.client.post("/lab/v4/session",json={"actor_id":A,"device_id":DEV_B,"demo_pin":PIN})
        self.assertEqual(r.status_code,401)

    def test_auth_required_for_private_balances(self):
        self.assertEqual(self.client.get("/lab/v4/me").status_code,401)

    def test_authenticated_me_read_only(self):
        bearer,device=self.auth[A]
        headers={"Authorization":"Bearer "+bearer,"X-Sim-Device":device}
        response=self.client.get("/lab/v4/me",headers=headers)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()["simulation"])
        self.assertFalse(response.json()["authoritative_balance"])

    def test_cross_role_audit_denied(self):
        bearer,device=self.auth[A]
        r=self.client.get("/lab/v4/audit-proof",headers={"Authorization":"Bearer "+bearer,"X-Sim-Device":device})
        self.assertEqual(r.status_code,403)

    def test_quote_and_review_over_http(self):
        bearer,device=self.auth[A]
        headers={"Authorization":"Bearer "+bearer,"X-Sim-Device":device}
        first=self.client.post("/lab/v4/quotes",json={"operation":"transfer","counterpart_id":B,
                 "principal_poisha":10000,"source_ref":"api_quote_00001"},headers=headers)
        self.assertEqual(first.status_code,200,first.text)
        item=first.json()
        review=self.client.post(f'/lab/v4/quotes/{item["quote_id"]}/review',json={"explicit_preview_consent":True},headers=headers)
        self.assertEqual(review.status_code,200,review.text)
        self.assertFalse(review.json()["financial_posting"])

    def test_forged_post_money_route_is_absent(self):
        bearer,device=self.auth[A]
        headers={"Authorization":"Bearer "+bearer,"X-Sim-Device":device}
        self.assertEqual(self.client.post("/lab/v4/ledger/post",json={},headers=headers).status_code,404)

    def test_remote_request_denied_even_with_valid_token(self):
        with TestClient(self.app,client=("203.0.113.99",60000)) as remote:
            self.assertEqual(remote.get("/lab/v4/health").status_code,403)

    def test_cannot_start_without_opt_in(self):
        with self.assertRaises(LabError):
            create_local_access_app(self.lab,explicitly_opted_in=False)

    def test_bad_content_length_denied(self):
        response=self.client.post("/lab/v4/session",content=b"x"*17000)
        self.assertEqual(response.status_code,413)


if __name__=="__main__":
    unittest.main()
