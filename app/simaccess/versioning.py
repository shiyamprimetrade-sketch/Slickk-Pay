"""Explicit compatibility negotiation for the isolated customer/agent lab.

A client must opt into the simulated API version, know whether data is cached,
and understand unsupported operations. Version matching is not production
identity assurance, payment authorization, or legal product approval.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from .errors import LabError,require

API_VERSION="lab-v4"
SCHEMA_MINOR=1
SUPPORTED_CLIENTS=frozenset({"android_lab_004","node_lab_004","python_lab_004"})
READ_ENDPOINTS=("/lab/v4/health","/lab/v4/capabilities","/lab/v4/me",
                "/lab/v4/activity","/lab/v4/quotes","/lab/v4/requests",
                "/lab/v4/support","/lab/v4/notifications")
PREVIEW_ENDPOINTS=("/lab/v4/session","/lab/v4/quotes","/lab/v4/support",
                   "/lab/v4/qr","/lab/v4/qr/inspect")
DISALLOWED_NETWORKS=frozenset({"npsb","binimoy","bkash_live","nagad_live","visa_live",
                               "mastercard_live","real_bank","live_loan"})


@dataclass(frozen=True)
class ClientHello:
    client_id:str
    api_version:str
    schema_minor:int
    accepts_simulation:bool
    expects_offline_payments:bool=False
    expects_real_bank:bool=False


@dataclass(frozen=True)
class Negotiation:
    accepted:bool
    client_id:str
    api_version:str
    schema_minor:int
    warnings:tuple[str,...]
    can_transact:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return {"accepted":self.accepted,"client_id":self.client_id,
                "api_version":self.api_version,"schema_minor":self.schema_minor,
                "warnings":list(self.warnings),"simulation":True,"can_transact":False,
                "bank_connected":False,"offline_payment":False}


class ContractVersionRegistry:
    def negotiate(self,hello:ClientHello)->Negotiation:
        require(isinstance(hello,ClientHello),"INVALID_INPUT")
        if hello.client_id not in SUPPORTED_CLIENTS:
            raise LabError("ROLE_FORBIDDEN")
        if not re.fullmatch(r"lab-v[1-9][0-9]*",hello.api_version):
            raise LabError("INVALID_INPUT")
        require(type(hello.schema_minor) is int and 0<=hello.schema_minor<=99,"INVALID_INPUT")
        warnings=[]
        accepted=hello.api_version==API_VERSION and hello.schema_minor<=SCHEMA_MINOR
        if not accepted:
            warnings.append("INCOMPATIBLE_LAB_CONTRACT")
        if hello.accepts_simulation is not True:
            warnings.append("SIMULATION_CONSENT_REQUIRED")
            accepted=False
        if hello.expects_offline_payments:
            warnings.append("OFFLINE_PAYMENTS_UNAVAILABLE")
            accepted=False
        if hello.expects_real_bank:
            warnings.append("REAL_BANK_UNAVAILABLE")
            accepted=False
        return Negotiation(accepted,hello.client_id,API_VERSION,SCHEMA_MINOR,tuple(warnings))

    def require_compatible(self,hello:ClientHello)->Negotiation:
        result=self.negotiate(hello)
        if not result.accepted:
            raise LabError("LAB_DISABLED")
        return result

    def manifest(self)->dict[str,object]:
        return {"api_version":API_VERSION,"schema_minor":SCHEMA_MINOR,
                "read_endpoints":list(READ_ENDPOINTS),"preview_endpoints":list(PREVIEW_ENDPOINTS),
                "supported_clients":sorted(SUPPORTED_CLIENTS),"live_networks_connected":[],
                "unsupported_networks":sorted(DISALLOWED_NETWORKS),
                "financial_posting_endpoints":[],"production_authorization":False,
                "fictional_only":True,"simulation":True}

    def changed_since(self,major:str,minor:int)->dict[str,object]:
        require(isinstance(major,str) and type(minor) is int,"INVALID_INPUT")
        changed=major!=API_VERSION or minor<SCHEMA_MINOR
        return {"changed":changed,"client_version":major,"client_minor":minor,
                "server_version":API_VERSION,"server_minor":SCHEMA_MINOR,
                "upgrade_may_enable_real_money":False,"simulation":True}
