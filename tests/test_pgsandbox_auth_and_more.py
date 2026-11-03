"""Strict synthetic HMAC replay, economics, reporting, and SQL parsing tests."""
import tempfile
import unittest
from pathlib import Path
from datetime import date
from fastapi.testclient import TestClient
from app.pgsandbox import SandboxStore, LedgerService
from app.pgsandbox.authz import SyntheticTokenService, KeyVersion
from app.pgsandbox.economics import ActivityMix, UnitEconomicsAssumptions,compute_margin,break_even_transactions
from app.pgsandbox.liquidity import DailyFlow,forecast_agent_liquidity
from app.pgsandbox.redaction import safe_diagnostic
from app.pgsandbox.reconciliation import ReconciliationService
from app.pgsandbox.api import create_inspection_app
from app.pgsandbox.pg_migrations import split_sql,sandbox_migration_proof
from app.pgsandbox.errors import AuthorizationError,InvalidValue


class ExtraFinanceTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix="sim-more-");self.addCleanup(t.cleanup)
        self.store=SandboxStore("sqlite+pysqlite:///"+str(Path(t.name)/"test.db"),local_test=True)
        self.addCleanup(self.store.dispose)
        self.ledger=LedgerService(self.store)
        self.ledger.open_account("sim_issuer_primary","sim_owner_issuer","sim_issuer")
        self.ledger.open_account("sim_customer_alpha","sim_owner_alpha","customer")
        self.ledger.transfer("sim_issuer_primary","sim_customer_alpha",5000,
                             key="issue:testing_more",actor="sim_operator_admin")

    def test_authorization_one_use_and_device_binding(self):
        service=SyntheticTokenService(self.store,(KeyVersion("sim_key_2026",b"Z"*32),),"sim_key_2026")
        token=service.issue(actor_id="sim_owner_alpha",scope="sim_inspect",device_id="sim_device_owned")
        with self.assertRaises(AuthorizationError):
            service.validate(token=token,scope="sim_inspect",actor_id="sim_owner_alpha",device_id="sim_device_other")
        grant=service.validate(token=token,scope="sim_inspect",actor_id="sim_owner_alpha",device_id="sim_device_owned")
        self.assertEqual(grant.scope,"sim_inspect")
        with self.assertRaises(AuthorizationError):
            service.validate(token=token,scope="sim_inspect",actor_id="sim_owner_alpha",device_id="sim_device_owned")

    def test_reconciliation_matches_internal_only(self):
        row=ReconciliationService(self.ledger).calculate("sim_customer_alpha",date.today().isoformat())
        self.assertTrue(row.matched)
        self.assertEqual(row.expected_poisha,5000)

    def test_operator_key_and_proof(self):
        k="K"*64
        client=TestClient(create_inspection_app(store=self.store,operator_key=k,explicitly_opted_in=True))
        self.assertEqual(client.get("/sim/v2/health").json()["interface"],"READ_ONLY")
        self.assertEqual(client.get("/sim/v2/proof").status_code,401)
        self.assertTrue(client.get("/sim/v2/proof",headers={"X-Sim-Operator-Key":k}).json()["valid"])
        self.assertEqual(client.post("/sim/v2/proof",headers={"X-Sim-Operator-Key":k}).status_code,405)
        self.assertEqual(client.post("/sim/v2/accounts/sim_customer_alpha",headers={"X-Sim-Operator-Key":k}).status_code,405)

    def test_redaction_and_money_math(self):
        result=safe_diagnostic("security_event",{"password":"do_not_share","email":"real@example.com"})
        self.assertNotIn("do_not_share",str(result))
        self.assertNotIn("real@example.com",str(result))
        mix=ActivityMix(10,20,5,10,100000,100000,100000,100000)
        r=compute_margin(mix,UnitEconomicsAssumptions(gateway_expense_ppm=2000,fixed_monthly_cost_poisha=100000))
        self.assertFalse(r.public()["break_even"])
        self.assertEqual(r.number_of_transactions,45)
        self.assertIsNone(break_even_transactions(principal_poisha=100000,mix="cash_in",
                            assumptions=UnitEconomicsAssumptions(),target_fixed_cost_poisha=10000))

    def test_liquidity_forecast(self):
        rows=(DailyFlow("2026-11-01",10000,30000),DailyFlow("2026-11-02",50000,1000))
        result=forecast_agent_liquidity(starting_cash_poisha=10000,
                        starting_float_poisha=100000,days=rows,minimum_cash_buffer_poisha=5000)
        self.assertEqual(result.required_additional_cash_poisha,15000)
        self.assertTrue(result.simulation)

    def test_migration_sql_parser_handles_function_body(self):
        statements=split_sql("SELECT ';' AS x; DO $$ BEGIN RAISE NOTICE ';'; END $$;")
        self.assertEqual(len(statements),2)
        self.assertGreater(sandbox_migration_proof().statement_count,10)
        with self.assertRaises(InvalidValue):
            split_sql("SELECT 'unterminated")

if __name__=="__main__": unittest.main()
