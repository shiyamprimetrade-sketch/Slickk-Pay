"""Independent gateway-vs-bank evidence reconciliation regression suite."""
import unittest
from dataclasses import replace
from datetime import datetime, timezone, timedelta

from app.ops.settlement import (
    GatewayRecord, BankCredit, GatewayState, SettlementState,
    Reconciler, StatementImporter,
)
from app.ops.primitives import EvidenceError, PolicyError

T=datetime(2026,11,3,12,0,tzinfo=timezone.utc)


def gateway(*, txn="T1", batch="B1", net=9750, gross=10000,
            fee=250, state=GatewayState.VALID, verified=True,
            risk=0, merchant="merchant-A", paid_at=T):
    return GatewayRecord(merchant,txn,"V"+txn,"bank"+txn,batch,gross,net,fee,
                         "BDT",state,verified,paid_at,risk)


def bank(*, batch="B1", ref="statement1", amount=9750,
         verified=True, merchant="merchant-A", posted_at=T+timedelta(hours=1)):
    return BankCredit(merchant,ref,batch,amount,"BDT",posted_at,verified)


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.recon=Reconciler()

    def run_report(self, rows=None, bank_rows=None, *, at=T+timedelta(days=1)):
        return self.recon.reconcile(merchant_id="merchant-A",
                gateway=[gateway()] if rows is None else rows,
                bank=[bank()] if bank_rows is None else bank_rows,as_of=at)

    def test_exact_match_is_settled_with_statement_evidence(self):
        report=self.run_report()
        self.assertTrue(report.reconciled)
        self.assertEqual(report.findings[0].state,SettlementState.SETTLED)
        self.assertEqual(report.provider_net_poisha,9750)
        self.assertEqual(report.bank_credit_poisha,9750)
        self.assertTrue(report.findings[0].bank_statement_verified)

    def test_gateway_net_is_separate_from_bank_deposit(self):
        report=self.run_report(bank_rows=[])
        self.assertFalse(report.reconciled)
        self.assertEqual(report.provider_net_poisha,9750)
        self.assertEqual(report.bank_credit_poisha,0)
        self.assertEqual(report.findings[0].state,SettlementState.PENDING_WITHIN_WINDOW)

    def test_overdue_bank_evidence(self):
        report=self.run_report(bank_rows=[],at=T+timedelta(days=4))
        self.assertEqual(report.missing_batches,1)
        self.assertEqual(report.findings[0].state,SettlementState.MISSING_BANK_EVIDENCE)

    def test_amount_mismatch_is_not_reconciled(self):
        report=self.run_report(bank_rows=[bank(amount=9700)])
        self.assertFalse(report.reconciled)
        self.assertEqual(report.mismatch_batches,1)
        self.assertEqual(report.findings[0].difference_poisha,-50)

    def test_duplicate_bank_statement_ref_is_error(self):
        report=self.run_report(bank_rows=[bank(),bank()])
        self.assertEqual(report.findings[0].state,SettlementState.DUPLICATE_REFERENCE)

    def test_multiple_bank_rows_same_batch_is_error(self):
        report=self.run_report(bank_rows=[bank(ref="S1",amount=5000),bank(ref="S2",amount=4750)])
        self.assertEqual(report.findings[0].state,SettlementState.DUPLICATE_REFERENCE)

    def test_duplicate_gateway_transaction_reference(self):
        report=self.run_report(rows=[gateway(),gateway()],bank_rows=[bank(amount=19500)])
        self.assertEqual(report.findings[0].state,SettlementState.DUPLICATE_REFERENCE)

    def test_multiple_gateway_items_in_one_batch(self):
        rows=[gateway(),gateway(txn="T2",net=4850,gross=5000,fee=150)]
        report=self.run_report(rows=rows,bank_rows=[bank(amount=14600)])
        self.assertTrue(report.reconciled)
        self.assertEqual(report.findings[0].transaction_count,2)
        self.assertEqual(report.provider_fee_poisha,400)

    def test_gateway_without_batch_is_not_settled(self):
        report=self.run_report(rows=[gateway(batch=None)],bank_rows=[])
        self.assertEqual(report.findings[0].state,SettlementState.UNBATCHED)

    def test_unmatched_bank_credit_is_not_settled(self):
        report=self.run_report(rows=[],bank_rows=[bank()])
        self.assertEqual(report.findings[0].state,SettlementState.UNMATCHED_BANK_CREDIT)

    def test_risk_flag_prevents_settlement_classification(self):
        for state,risk in ((GatewayState.REVIEW,1),(GatewayState.DISPUTED,0),
                           (GatewayState.VALIDATED,1)):
            with self.subTest(state=state):
                report=self.run_report(rows=[gateway(state=state,risk=risk)])
                self.assertEqual(report.findings[0].state,SettlementState.RISK_HELD)

    def test_failed_and_cancelled_are_not_payable(self):
        for state in (GatewayState.FAILED,GatewayState.CANCELLED,GatewayState.REFUNDED):
            with self.subTest(state=state):
                report=self.run_report(rows=[gateway(state=state)])
                self.assertEqual(report.findings[0].state,SettlementState.NOT_PAYABLE)

    def test_missing_gateway_verification(self):
        report=self.run_report(rows=[gateway(verified=False)])
        self.assertEqual(report.findings[0].state,SettlementState.INVALID_GATEWAY_EVIDENCE)

    def test_unverified_bank_statement_is_not_settled(self):
        report=self.run_report(bank_rows=[bank(verified=False)])
        self.assertEqual(report.findings[0].state,SettlementState.MISSING_BANK_EVIDENCE)

    def test_bank_verification_policy_cannot_be_disabled(self):
        with self.assertRaises(PolicyError):
            Reconciler(require_bank_verification=False)

    def test_bank_deposit_predates_payment(self):
        report=self.run_report(bank_rows=[bank(posted_at=T-timedelta(days=1))])
        self.assertEqual(report.findings[0].state,SettlementState.INVALID_GATEWAY_EVIDENCE)

    def test_cross_merchant_records_rejected(self):
        with self.assertRaises(PolicyError):
            self.run_report(rows=[gateway(merchant="merchant-B")])
        with self.assertRaises(PolicyError):
            self.run_report(bank_rows=[bank(merchant="merchant-B")])

    def test_future_bank_record_rejected(self):
        with self.assertRaises(EvidenceError):
            self.run_report(bank_rows=[bank(posted_at=T+timedelta(days=10))])

    def test_invalid_money_math_rejected(self):
        with self.assertRaises(EvidenceError):
            gateway(net=9700,fee=250)
        with self.assertRaises(EvidenceError):
            bank(amount=0)

    def test_reconciliation_digest_is_stable(self):
        first=self.run_report()
        second=self.run_report()
        self.assertEqual(first.evidence_digest,second.evidence_digest)
        self.assertEqual(len(first.evidence_digest),64)

    def test_public_output_does_not_claim_bank_transfer(self):
        report=self.run_report()
        output=report.as_dict()
        self.assertFalse(output["bank_settlement_executed_by_software"])
        self.assertEqual(output["provider_reported_net_bdt"],"97.50")


class StatementImporterTests(unittest.TestCase):
    def setUp(self):
        self.importer=StatementImporter()

    def test_gateway_csv_roundtrip(self):
        original=(gateway(),gateway(txn="T2",batch="B2",net=9700,fee=300))
        raw=self.importer.render_gateway_csv(original)
        recovered=self.importer.gateway_rows(raw)
        self.assertEqual(recovered,original)
        self.assertNotIn("cus_email",raw)
        self.assertNotIn("card_no",raw)

    def test_bank_csv_roundtrip(self):
        original=(bank(),bank(batch="B2",ref="statement2",amount=3450))
        raw=self.importer.render_bank_csv(original)
        recovered=self.importer.bank_rows(raw)
        self.assertEqual(recovered,original)

    def test_csv_rejects_unapproved_private_fields(self):
        raw=self.importer.render_bank_csv([bank()])
        with self.assertRaises(EvidenceError):
            self.importer.bank_rows(raw.replace("batch_ref,","card_no,batch_ref,"))

    def test_csv_rejects_duplicate_columns(self):
        raw=self.importer.render_bank_csv([bank()])
        header=raw.splitlines()[0]
        with self.assertRaises(EvidenceError):
            self.importer.bank_rows(header+",merchant_id\n"+raw.splitlines()[1]+",foo\n")

    def test_csv_rejects_extra_fields(self):
        raw=self.importer.render_bank_csv([bank()])
        with self.assertRaises(EvidenceError):
            self.importer.bank_rows(raw+"additional,not,a,proper,row,with,many,fields\n")

    def test_csv_row_limit(self):
        limited=StatementImporter(max_rows=1)
        raw=self.importer.render_bank_csv([bank(),bank(ref="S2")])
        with self.assertRaises(EvidenceError):
            limited.bank_rows(raw)

    def test_csv_rejects_invalid_boolean(self):
        raw=self.importer.render_bank_csv([bank()])
        with self.assertRaises(EvidenceError):
            self.importer.bank_rows(raw.replace("true","yes"))

    def test_csv_rejects_null_byte(self):
        with self.assertRaises(EvidenceError):
            self.importer.bank_rows("\x00bad csv")


if __name__=="__main__":
    unittest.main()
