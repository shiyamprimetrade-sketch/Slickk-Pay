"""API smoke tests (still entirely simulated; no network services)."""
import os
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

TMP = tempfile.TemporaryDirectory()
os.environ['SLICKK_DB'] = str(Path(TMP.name) / 'api.sqlite3')
from app.main import app  # noqa: E402


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.post('/api/demo/reset')

    def test_home_and_dashboard(self):
        html = self.client.get('/')
        self.assertEqual(html.status_code, 200)
        self.assertIn('SANDBOX MODE', html.text)
        dashboard = self.client.get('/api/dashboard')
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(dashboard.json()['mode'], 'SANDBOX_ONLY')

    def test_transfer_http_and_bad_request(self):
        data = {'sender_id':'alice','recipient_id':'rahim','amount_bdt':'12.34','request_id':'req-transfer-001'}
        self.assertEqual(self.client.post('/api/transfers', json=data).status_code, 200)
        self.assertEqual(self.client.post('/api/transfers', json=data).status_code, 200)
        self.assertEqual(self.client.get('/api/audit').json()['balanced'], True)
        data['amount_bdt'] = '-5'
        self.assertEqual(self.client.post('/api/transfers', json=data).status_code, 400)

    def test_credit_loan_and_repay_http(self):
        body = {'borrower_id':'alice','biller_id':'school','category':'education','amount_bdt':'500','term_days':15}
        quote = self.client.post('/api/credit/quote', json=body)
        self.assertEqual(quote.status_code, 200)
        self.assertEqual(quote.json()['fee_bdt'], '8.00')
        credit = self.client.post('/api/credit/simulate', json={**body,'request_id':'req-credit-001'})
        self.assertEqual(credit.status_code, 200)
        loan = credit.json()['loan_id']
        repaid = self.client.post(f'/api/credit/{loan}/repay', json={'borrower_id':'alice','request_id':'req-repay-001'})
        self.assertEqual(repaid.status_code, 200)
        self.assertEqual(repaid.json()['amount_bdt'], '508.00')
        self.assertTrue(self.client.get('/api/audit').json()['balanced'])


if __name__ == '__main__': unittest.main()
