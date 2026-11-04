"""Application composition root for the non-settling synthetic access lab.

The financial ledger and merchant checkout are not imported here. Services
share the same local-only SQLite database for access/draft atomicity, but have
no authority to change actual account balances or call an external gateway.
"""
from __future__ import annotations
from dataclasses import dataclass
from .audit import AccessAudit
from .cash import AgentCashChecklist
from .cash_dialogue import CashDialogue
from .clock import Clock
from .crypto import KeyRing, SigningKey
from .errors import LabError,require
from .identity import IdentityRegistry
from .outbox import LabOutbox
from .policy import AccessPolicy
from .pricing import PricingEngine
from .privacy import PrivacyInspector
from .qr import SampleQrService
from .quotes import QuoteService
from .rate_limits import RateLimiter
from .receipts import ReceiptService
from .reports import LabReports
from .risk import SyntheticRiskEngine
from .device_policy import DevicePolicy
from .directory import AgentDirectory, default_sample_agents
from .search import ActivitySearch
from .disclosures import DisclosureService
from .versioning import ContractVersionRegistry
from .consistency import ConsistencyAuditor
from .recovery import LabRecovery
from .requests import RequestService
from .sessions import SessionManager, SessionContext
from .store import LabStore
from .support import SupportService


@dataclass(frozen=True)
class ServiceCapabilities:
    simulation:bool=True
    can_move_money:bool=False
    accepts_deposits:bool=False
    allows_cash_handover:bool=False
    cash_authorization:bool=False
    can_issue_loans:bool=False
    bank_connected:bool=False
    checkout_provider_connected:bool=False
    customer_auth_mode:str="SYNTHETIC_FIXTURE_ONLY"
    api_revision:str="lab-v4"

    def public(self)->dict[str,object]:
        return dict(self.__dict__)


class AccessLab:
    def __init__(self,store:LabStore,*,qr_keyring:KeyRing|None=None):
        self.store=store
        self.identity=IdentityRegistry(store)
        self.sessions=SessionManager(store)
        self.policy=AccessPolicy()
        self.pricing=PricingEngine()
        self.quotes=QuoteService(store,self.pricing)
        self.requests=RequestService(store)
        self.receipts=ReceiptService(store)
        self.reports=LabReports(store)
        self.risk=SyntheticRiskEngine()
        self.device_policy=DevicePolicy()
        self.directory=AgentDirectory(store,default_sample_agents())
        self.search=ActivitySearch(store)
        self.disclosures=DisclosureService(self.pricing)
        self.versions=ContractVersionRegistry()
        self.consistency=ConsistencyAuditor(store)
        self.cash=AgentCashChecklist(store)
        self.cash_dialogue=CashDialogue(store)
        self.support=SupportService(store)
        self.notifications=LabOutbox(store)
        self.recovery=LabRecovery(store)
        self.audit=AccessAudit(store)
        self.rates=RateLimiter(store)
        self.privacy=PrivacyInspector()
        self.qr=SampleQrService(store,qr_keyring) if qr_keyring else None
        self.capabilities=ServiceCapabilities()
        AccessPolicy.assert_no_money_posting()
        self.recovery.assert_no_financial_posting()

    def context(self,*,bearer:str,device_id:str)->SessionContext:
        return self.sessions.require(bearer=bearer,device_id=device_id)

    def summary(self,context:SessionContext)->dict[str,object]:
        AccessPolicy.require(context,"profile:read",resource_owner=context.actor_id)
        persona=self.identity.get(context.actor_id)
        balances=self.identity.sample_balances(context.actor_id) if context.role!="operator" else []
        return {"persona":persona.public(),"accounts":balances,
                "capabilities":self.capabilities.public(),"simulation":True,
                "currency":"BDT","authoritative_balance":False}

    def full_health(self)->dict[str,object]:
        result=self.store.health()
        proof=self.audit.verify()
        return {**result,"audit_valid":proof.valid,"posting_enabled":False,
                "provider_network_connections":0}

    def operator_proof(self,context:SessionContext)->dict[str,object]:
        AccessPolicy.require(context,"audit:read",resource_owner=context.actor_id)
        if context.role!="operator":
            raise LabError("ROLE_FORBIDDEN")
        return self.audit.public_summary()

    def publish_money_event(self,*_:object,**__:object)->None:
        from .errors import deny_posting
        deny_posting()

    def credits(self,*_:object,**__:object)->None:
        from .errors import deny_posting
        deny_posting()

    def settlement(self,*_:object,**__:object)->None:
        from .errors import deny_posting
        deny_posting()


def create_local_lab(database_path:str,*,opted_in:bool,
                     qr_keyring:KeyRing|None=None,clock:Clock|None=None)->AccessLab:
    store=LabStore(database_path,opted_in=opted_in,clock=clock)
    return AccessLab(store,qr_keyring=qr_keyring)
