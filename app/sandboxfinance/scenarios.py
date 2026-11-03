"""Reproducible, offline finance-lab scenarios for cross-module acceptance checks.

The orchestrator intentionally has no external networking, no persistent
production credentials and no financial side effects outside its sandbox DB.
Every returned metric is explicitly fictional and should not be used in public
merchant reporting, bank statements or underwriting decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .identity import SyntheticRegistry,Party,synthetic_customer,synthetic_agent
from .ledger import SandboxLedger
from .workflows import CashDesk,CustomerTransfers,prepare_synthetic_system
from .gateway import InternalMerchantGateway
from .loans import SyntheticLoanBook,BorrowerEvidence
from .agency import AgentLiquidityDesk
from .reports import SandboxReports
from .pricing import poisha_to_bdt


@dataclass(frozen=True)
class ScenarioResult:
    scenario_id:str
    posted_events:int
    journal_lines:int
    customer_balances_poisha:dict[str,int]
    merchant_balance_poisha:int
    agent_float_poisha:int
    simulated_cash_position_poisha:int
    synthetic_loan_state:str
    invariant_balanced:bool
    simulation:bool=True
    actual_money_moved_poisha:int=0


class FinanceScenario:
    """Build all accounts and execute one representative, imaginary end-to-end flow."""

    def __init__(self,path:str|Path):
        self.ledger=SandboxLedger(path)
        self.registry=SyntheticRegistry()
        self.people=(
            synthetic_customer("testalice","01711111111","Alice Synthetic"),
            synthetic_customer("testbob","01822222222","Bob Synthetic"),
            synthetic_agent("testagent","01933333333","Agent Synthetic"),
            Party("sim_testmerchant","merchant","Merchant Synthetic","01644444444"),
            Party("sim_testoperator","operator","Operator Synthetic","01555555555"),
        )
        for party in self.people:
            self.registry.register(party)
            self.registry.approve_sandbox(party.party_id)
        prepare_synthetic_system(self.ledger,self.registry)
        self.cash=CashDesk(self.ledger,self.registry)
        self.transfers=CustomerTransfers(self.ledger,self.registry)
        self.gateway=InternalMerchantGateway(self.ledger,self.registry)
        self.loans=SyntheticLoanBook(self.ledger,self.registry)
        self.agency=AgentLiquidityDesk(self.ledger,self.registry)
        self.reports=SandboxReports(self.ledger)

    def fund_test_accounts(self)->None:
        """Synthetic issuance remains balanced with a matching issuer liability."""
        allocations=(
            ("sim_wallet_testalice",3_000_000,"scenario-issue-alice"),
            ("sim_wallet_testbob",500_000,"scenario-issue-bob"),
            ("sim_float_testagent",4_000_000,"scenario-issue-agent"),
            ("sim_platform_treasury",5_000_000,"scenario-issue-treasury"),
        )
        for account,amount,reference in allocations:
            self.ledger.synthetic_issue(account,amount,reference=reference)
        self.cash.register_agent_cash("sim_testagent",reported_cash_poisha=1_000_000,
                                      limit_poisha=5_000_000)

    def execute(self)->ScenarioResult:
        """Run synthetic transfer, cash-in, cash-out, merchant checkout and credit case."""
        self.fund_test_accounts()
        self.transfers.send(sender_id="sim_testalice",recipient_id="sim_testbob",
                            principal=100_000,reference="scenario-customer-transfer",
                            customer_confirmed=True)
        incoming=self.cash.request_cash_in("sim_testalice","sim_testagent",50_000)
        self.cash.confirm(incoming.request.request_id,agent_id="sim_testagent",
                          customer_token=incoming.customer_token,cash_handover_confirmed=True)
        outgoing=self.cash.request_cash_out("sim_testbob","sim_testagent",30_000)
        self.cash.confirm(outgoing.request.request_id,agent_id="sim_testagent",
                          customer_token=outgoing.customer_token,cash_handover_confirmed=True)
        merchant_secret="synthetic-merchant-test-key-111111111111111"
        self.gateway.register_merchant("sim_testmerchant",merchant_secret)
        payment=self.gateway.create_intent(merchant_id="sim_testmerchant",merchant_key=merchant_secret,
                                           customer_id="sim_testalice",invoice_ref="scenario-invoice-001",
                                           principal_poisha=20_000)
        self.gateway.capture(payment.intent.intent_id,customer_id="sim_testalice",
                             customer_approval_token=payment.customer_approval_token)
        borrowing=BorrowerEvidence("sim_testalice",200_000,50_000,0,700)
        application,assessment=self.loans.apply(evidence=borrowing,
                                                 principal_poisha=100_000,term_months=3)
        self.loans.decide(application.application_id,operator_id="sim_testoperator",
                          approve=True,assessment=assessment,
                          explanation="synthetic_policy_eligible")
        self.loans.disburse(application.application_id,operator_id="sim_testoperator")
        self.loans.pay_next(application.application_id,customer_id="sim_testalice")
        verified=self.ledger.verify()
        return ScenarioResult(
            "fictional-cycle001-acceptance",verified["events"],verified["posting_lines"],
            {name:self.ledger.account(name).balance_poisha for name in
             ("sim_wallet_testalice","sim_wallet_testbob")},
            self.ledger.account("sim_merchant_testmerchant").balance_poisha,
            self.ledger.account("sim_float_testagent").balance_poisha,
            self.cash.cash_available("sim_testagent"),
            self.loans.case(application.application_id).status,
            verified["net_poisha"]==0)

    def snapshot(self)->dict[str,Any]:
        output=self.reports.compact_snapshot()
        output["explicit_test_scenario"]="fictional-cycle001-acceptance"
        output["live_licensing_status"]="not asserted"
        output["verified_bank_settlement"]="none"
        return output
