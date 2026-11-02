import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from app.core import Store, DomainError, taka_to_poisha, quote_fee


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "bank.sqlite3"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_and_audit(self):
        d = self.store.dashboard()
        self.assertEqual(next(a for a in d['accounts'] if a['id'] == 'alice')['balance_bdt'], '7500.00')
        self.assertTrue(self.store.ledger_audit()['balanced'])

    def test_transfer_balances(self):
        result = self.store.transfer('alice', 'rahim', '123.45', 'transfer-001')
        self.assertEqual(result['amount_bdt'], '123.45')
        acc = {a['id']: a for a in self.store.dashboard()['accounts']}
        self.assertEqual(acc['alice']['balance_bdt'], '7376.55')
        self.assertEqual(acc['rahim']['balance_bdt'], '3373.45')
        self.assertTrue(self.store.ledger_audit()['balanced'])

    def test_idempotent_transfer(self):
        a = self.store.transfer('alice', 'rahim', '60', 'transfer-001')
        b = self.store.transfer('alice', 'rahim', '60', 'transfer-001')
        self.assertEqual(a, b)
        self.assertEqual(self.store.dashboard()['accounts'][0]['balance_bdt'], '7440.00')

    def test_idempotency_reuse_rejected(self):
        self.store.transfer('alice', 'rahim', '60', 'transfer-001')
        with self.assertRaises(DomainError):
            self.store.transfer('alice', 'rahim', '61', 'transfer-001')

    def test_invalid_amount_rejected(self):
        for value in ('0', '-1', 'NaN', 'Infinity', '1.001', 'abc'):
            with self.subTest(value=value), self.assertRaises(DomainError):
                taka_to_poisha(value)

    def test_unfunded_transfer_rejected_without_mutation(self):
        before = self.store.dashboard()
        with self.assertRaises(DomainError):
            self.store.transfer('alice', 'rahim', '9000', 'transfer-001')
        self.assertEqual(before, self.store.dashboard())

    def test_payment_restricts_to_merchant(self):
        with self.assertRaises(DomainError):
            self.store.transfer('alice', 'rahim', '5', 'payment-001', payment=True)
        self.store.transfer('alice', 'shop', '5', 'payment-002', payment=True)
        self.assertTrue(self.store.ledger_audit()['balanced'])

    def test_fee_boundaries(self):
        self.assertEqual(quote_fee(50*100, 7), 300)
        self.assertEqual(quote_fee(250*100, 30), 600)
        self.assertEqual(quote_fee(1000*100, 7), 700)
        self.assertEqual(quote_fee(1001*100, 7), 1000)
        self.assertEqual(quote_fee(10000*100, 30), 13000)
        for amount, term in [(49*100, 7), (10001*100, 7), (100*100, 8)]:
            with self.assertRaises(DomainError): quote_fee(amount, term)

    def test_credit_only_to_eligible_biller(self):
        with self.assertRaises(DomainError):
            self.store.credit_quote('alice', 'shop', 'utility', '500', 7)
        with self.assertRaises(DomainError):
            self.store.credit_quote('alice', 'rahim', 'utility', '500', 7)
        quote = self.store.credit_quote('alice', 'electric', 'utility', '500', 7)
        self.assertEqual(quote['total_due_bdt'], '505.00')
        self.assertEqual(quote['decision'], 'NO_REAL_CREDIT_APPROVAL')

    def test_credit_direct_to_biller_and_full_repayment(self):
        before = {a['id']:a for a in self.store.dashboard()['accounts']}
        r = self.store.credit_simulate('alice','electric','utility','1000',7,'credit-001')
        after = {a['id']:a for a in self.store.dashboard()['accounts']}
        self.assertEqual(before['alice']['balance_bdt'], after['alice']['balance_bdt'])
        self.assertEqual(after['electric']['balance_bdt'], '1000.00')
        self.assertEqual(r['total_due_bdt'], '1007.00')
        paid = self.store.repay(r['loan_id'], 'alice', 'repayment-001')
        self.assertEqual(paid['amount_bdt'], '1007.00')
        self.assertEqual(self.store.dashboard()['loans'][0]['status'], 'repaid')
        self.assertTrue(self.store.ledger_audit()['balanced'])

    def test_repayment_wrong_customer_and_repeat(self):
        r = self.store.credit_simulate('alice','electric','utility','100',7,'credit-001')
        with self.assertRaises(DomainError):
            self.store.repay(r['loan_id'], 'rahim', 'repayment-001')
        a = self.store.repay(r['loan_id'], 'alice', 'repayment-001')
        self.assertEqual(a, self.store.repay(r['loan_id'], 'alice', 'repayment-001'))
        with self.assertRaises(DomainError):
            self.store.repay(r['loan_id'], 'alice', 'repayment-002')

    def test_no_second_open_credit(self):
        self.store.credit_simulate('alice','electric','utility','100',7,'credit-001')
        with self.assertRaises(DomainError):
            self.store.credit_simulate('alice','school','education','100',7,'credit-002')

    def test_concurrent_spending_does_not_overdraft(self):
        def work(i):
            try:
                self.store.transfer('alice', 'rahim', '6000', f'concurrent-{i:04d}')
                return True
            except DomainError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            successes = list(pool.map(work, range(2)))
        self.assertEqual(sum(successes), 1)
        self.assertTrue(self.store.ledger_audit()['balanced'])


if __name__ == '__main__':
    unittest.main()
