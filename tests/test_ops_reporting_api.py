"""Read-only staging route, data-masking and readiness evidence acceptance."""
import unittest
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ops.api import OpsPreviewConfig, create_ops_router
from app.ops.reports import (
    ReadinessChecklist, VerificationGate, GateStatus, ReportingEngine,
)
from app.ops.settlement import Reconciler
from app.ops.risk import RiskAssessment, Decision
from app.ops.disputes import DisputeDesk
from app.ops.journal import ShadowJournal
from app.ops.primitives import EvidenceError
from tests.test_ops_settlement import gateway,bank

T=datetime(2026,11,3,12,0,tzinfo=timezone.utc)
AUTH_KEY="sandbox-merchant-api-key-at-least-32-characters"
AUTH={"X-Slickk-Api-Key":AUTH_KEY}


def app_for(*,enabled=True, environment="staging"):
    app=FastAPI()
    app.include_router(create_ops_router(OpsPreviewConfig(
        environment=environment,merchant_api_key=AUTH_KEY,enabled=enabled)))
    return TestClient(app)


def gateway_json():
    return {"merchant_id":"merchant-A", "tran_id":"T1", "val_id":"V1",
            "bank_tran_id":"bank1", "batch_ref":"B1",
            "gross_bdt":"100.00", "net_bdt":"97.50", "fee_bdt":"2.50",
            "state":"valid", "verified":True,"risk_level":0,
            "paid_at":"2026-11-03T12:00:00Z"}


def bank_json():
    return {"merchant_id":"merchant-A","statement_ref":"s1","batch_ref":"B1",
            "amount_bdt":"97.50", "posted_at":"2026-11-03T13:00:00Z",
            "statement_verified":True}


def reconcile_body():
    return {"merchant_id":"merchant-A", "as_of":"2026-11-05T12:00:00Z",
            "gateway":[gateway_json()], "bank":[bank_json()]}


def risk_body():
    return {"merchant_id":"merchant-A", "transaction_id":"T1", "order_ref":"ord-1",
            "amount_bdt":"100.00","created_at":"2026-11-03T12:00:00Z",
            "now":"2026-11-03T12:00:00Z", "gateway_verified":True,
            "gateway_risk_level":0,"invoice_authorized":True}


class OperationsAPITests(unittest.TestCase):
    def setUp(self):
        self.client=app_for()

    def test_public_contract_truthful(self):
        response=self.client.get("/v1/ops/contract")
        self.assertEqual(response.status_code,200)
        info=response.json()
        self.assertFalse(info["payment_provider_requests"])
        self.assertFalse(info["bank_statements_independently_verified_by_api"])
        self.assertEqual(info["persistence"],"none")

    def test_disabled_by_default(self):
        client=app_for(enabled=False)
        response=client.post("/v1/ops/reconcile/preview",headers=AUTH,json=reconcile_body())
        self.assertEqual(response.status_code,503)
        self.assertFalse(client.get("/v1/ops/contract").json()["enabled"])

    def test_missing_or_wrong_auth(self):
        for headers in ({},{"X-Slickk-Api-Key":"bad"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post("/v1/ops/risk/preview",
                    headers=headers,json=risk_body()).status_code,401)

    def test_production_ops_preview_cannot_be_enabled(self):
        with self.assertRaises(ValueError):
            OpsPreviewConfig(environment="production",merchant_api_key=AUTH_KEY,enabled=True)

    def test_enabled_preview_requires_strong_key(self):
        with self.assertRaises(ValueError):
            OpsPreviewConfig(environment="staging",merchant_api_key="weak",enabled=True)

    def test_reconciliation_exact_gateway_bank_record(self):
        response=self.client.post("/v1/ops/reconcile/preview",headers=AUTH,json=reconcile_body())
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertTrue(data["preview"]["reconciled"])
        self.assertFalse(data["real_bank_settlement_confirmed"])
        self.assertFalse(data["financial_state_mutated"])

    def test_reconciliation_no_bank_evidence(self):
        body=reconcile_body()
        body["bank"]=[]
        response=self.client.post("/v1/ops/reconcile/preview",headers=AUTH,json=body)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()["preview"]["reconciled"])

    def test_reconciliation_amount_mismatch(self):
        body=reconcile_body()
        body["bank"][0]["amount_bdt"]="97.00"
        response=self.client.post("/v1/ops/reconcile/preview",headers=AUTH,json=body)
        self.assertEqual(response.json()["preview"]["findings"][0]["state"],"amount_mismatch")

    def test_reconciliation_rejects_cross_merchant_bank(self):
        body=reconcile_body()
        body["bank"][0]["merchant_id"]="merchant-B"
        self.assertEqual(self.client.post("/v1/ops/reconcile/preview",
            headers=AUTH,json=body).status_code,422)

    def test_reconciliation_rejects_float_amount(self):
        body=reconcile_body()
        body["gateway"][0]["gross_bdt"]=100.00
        self.assertEqual(self.client.post("/v1/ops/reconcile/preview",
            headers=AUTH,json=body).status_code,422)

    def test_reconciliation_rejects_extra_private_fields(self):
        body=reconcile_body()
        body["gateway"][0]["card_number"]="4111111111111111"
        self.assertEqual(self.client.post("/v1/ops/reconcile/preview",
            headers=AUTH,json=body).status_code,422)

    def test_risk_low_amount_is_preview_only(self):
        response=self.client.post("/v1/ops/risk/preview",headers=AUTH,json=risk_body())
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["preview"]["decision"],"allow_to_validate")
        self.assertFalse(response.json()["financial_state_mutated"])

    def test_risk_provider_high_risk_hold(self):
        body=risk_body()
        body["gateway_risk_level"]=1
        response=self.client.post("/v1/ops/risk/preview",headers=AUTH,json=body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["preview"]["decision"],"hold_provider_risk")

    def test_risk_missing_gateway_validation_hold(self):
        body=risk_body()
        body["gateway_verified"]=False
        body["gateway_risk_level"]=None
        response=self.client.post("/v1/ops/risk/preview",headers=AUTH,json=body)
        self.assertEqual(response.json()["preview"]["decision"],"hold_missing_evidence")

    def test_readiness_omitted_gates_never_reports_ready(self):
        body={"merchant_id":"merchant-A","as_of":"2026-11-03T12:00:00Z","gates":[]}
        response=self.client.post("/v1/ops/readiness/preview",headers=AUTH,json=body)
        self.assertEqual(response.status_code,200)
        self.assertFalse(response.json()["preview"]["production_ready"])
        self.assertGreater(len(response.json()["missing_gates"]),0)

    def test_readiness_forged_evidence_digest_rejected(self):
        body={"merchant_id":"merchant-A","as_of":"2026-11-03T12:00:00Z",
              "gates":[{"gate_id":"credential_rotation","status":"passed",
                        "evidence_digest":"bogus"}]}
        self.assertEqual(self.client.post("/v1/ops/readiness/preview",
            headers=AUTH,json=body).status_code,422)


class ReportingTests(unittest.TestCase):
    def test_evidence_checklist_requires_all_gates(self):
        checklist=ReadinessChecklist()
        gates=[VerificationGate(name,GateStatus.PASSED,"a"*64,"reviewer-A")
               for name in checklist.REQUIRED]
        assessment=checklist.assess(merchant_id="merchant-A",now=T,gates=gates)
        self.assertTrue(assessment.all_claimed_gates_passed)
        self.assertFalse(assessment.as_dict()["production_ready"])
        self.assertEqual(checklist.missing(gates),())
        self.assertFalse(assessment.as_dict()["financial_activity_authorized_by_this_report"])

    def test_one_missing_gate_blocks_readiness(self):
        checklist=ReadinessChecklist()
        gates=[VerificationGate(name,GateStatus.PASSED,"a"*64,"reviewer-A")
               for name in sorted(checklist.REQUIRED)[:-1]]
        result=checklist.assess(merchant_id="merchant-A",now=T,gates=gates)
        self.assertFalse(result.all_claimed_gates_passed)
        self.assertEqual(len(checklist.missing(gates)),1)

    def test_duplicate_evidence_gate_rejected(self):
        gate=VerificationGate("staging_deployment",GateStatus.PENDING,None,None)
        with self.assertRaises(EvidenceError):
            ReadinessChecklist().assess(merchant_id="merchant-A",now=T,gates=[gate,gate])

    def test_report_combines_no_money_movement(self):
        reconciliation=Reconciler().reconcile(merchant_id="merchant-A",
            gateway=[gateway()],bank=[bank()],as_of=T+timedelta(days=1))
        snapshot=ReportingEngine().create_snapshot(merchant_id="merchant-A",
            at=T+timedelta(days=1),reconciliation=reconciliation,risk=[],
            journal=ShadowJournal(),disputes=DisputeDesk())
        public=snapshot.public_dict()
        self.assertEqual(public["provider_gross_bdt"],"100.00")
        self.assertEqual(public["bank_evidence_bdt"],"97.50")
        self.assertFalse(public["regulatory_report_submitted"])
        self.assertFalse(public["bank_settlement_authorized"])

    def test_snapshot_rejects_cross_merchant_evidence(self):
        reconciliation=Reconciler().reconcile(merchant_id="merchant-A",
            gateway=[],bank=[],as_of=T)
        with self.assertRaises(EvidenceError):
            ReportingEngine().create_snapshot(merchant_id="merchant-B",at=T,
                reconciliation=reconciliation,risk=[],journal=ShadowJournal(),
                disputes=DisputeDesk())

    def test_snapshot_comparison_time_order(self):
        reconciliation=Reconciler().reconcile(merchant_id="merchant-A",
            gateway=[],bank=[],as_of=T)
        engine=ReportingEngine()
        first=engine.create_snapshot(merchant_id="merchant-A",at=T,
            reconciliation=reconciliation,risk=[],journal=ShadowJournal(),disputes=DisputeDesk())
        second=engine.create_snapshot(merchant_id="merchant-A",at=T+timedelta(minutes=1),
            reconciliation=reconciliation,risk=[],journal=ShadowJournal(),disputes=DisputeDesk())
        change=engine.compare_snapshots(first,second)
        self.assertEqual(change["change_provider_gross_bdt"],"0.00")
        with self.assertRaises(EvidenceError):
            engine.compare_snapshots(second,first)


if __name__=="__main__":
    unittest.main()
