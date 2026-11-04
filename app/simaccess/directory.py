"""Synthetic agent-directory discovery, with coarse regions and no real GPS.

Agents listed here are fictional fixtures and their sample capacity must
never be interpreted as the actual cash available for a public cash-out.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .identifiers import synthetic_id,minor_units
from .identity import IdentityRegistry
from .sessions import SessionContext
from .policy import AccessPolicy
from .store import LabStore

REGIONS=frozenset({"dhaka_demo","chattogram_demo","khulna_demo","sylhet_demo","rajshahi_demo"})


@dataclass(frozen=True)
class AgentListing:
    actor_id:str
    display_label:str
    region:str
    sample_cash_poisha:int
    sample_float_poisha:int
    enabled:bool=True
    verified_business_location:bool=False
    real_agent_registered:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return {"actor_id":self.actor_id,"label":self.display_label,"region":self.region,
                "sample_cash_poisha":self.sample_cash_poisha,
                "sample_float_poisha":self.sample_float_poisha,
                "accepts_real_cash":False,"verified_business_location":False,
                "registered_financial_agent":False,"simulation":True}


class AgentDirectory:
    def __init__(self,store:LabStore,listing:tuple[AgentListing,...]=()):
        self.store=store
        self.identity=IdentityRegistry(store)
        self._listings={}
        for item in listing:
            self.add(item)

    def add(self,item:AgentListing)->None:
        require(isinstance(item,AgentListing),"INVALID_INPUT")
        synthetic_id(item.actor_id)
        require(item.region in REGIONS,"INVALID_INPUT")
        minor_units(item.sample_cash_poisha,zero_ok=True)
        minor_units(item.sample_float_poisha,zero_ok=True)
        require(item.verified_business_location is False and item.real_agent_registered is False,"INVALID_INPUT")
        if item.actor_id in self._listings:
            raise LabError("CONFLICT")
        self._listings[item.actor_id]=item

    def search(self,context:SessionContext,*,region:str|None=None,
               minimum_sample_cash_poisha:int=0,limit:int=25)->dict[str,object]:
        AccessPolicy.require(context,"profile:read",resource_owner=context.actor_id)
        if region is not None:
            require(region in REGIONS,"INVALID_INPUT")
        minor_units(minimum_sample_cash_poisha,zero_ok=True)
        require(type(limit) is int and 1<=limit<=100,"INVALID_INPUT")
        results=[]
        for item in sorted(self._listings.values(),key=lambda x:(x.region,x.display_label,x.actor_id)):
            if not item.enabled or (region is not None and item.region!=region):
                continue
            if item.sample_cash_poisha<minimum_sample_cash_poisha:
                continue
            try:
                actor=self.identity.get(item.actor_id)
            except LabError:
                continue
            if actor.role!="agent" or actor.state!="active":
                continue
            results.append(item.public())
        return {"items":results[:limit],"has_more":len(results)>limit,
                "total_matching":len(results),"simulation":True,
                "current_open_hours_unverified":True,"real_location_verified":False}

    def compare_float(self,context:SessionContext,*,agent_id:str,
                      requested_cash_poisha:int)->dict[str,object]:
        AccessPolicy.require(context,"profile:read",resource_owner=context.actor_id)
        synthetic_id(agent_id)
        minor_units(requested_cash_poisha)
        item=self._listings.get(agent_id)
        if item is None or not item.enabled:
            raise LabError("NOT_FOUND")
        available=item.sample_cash_poisha
        return {"agent_id":agent_id,"request_poisha":requested_cash_poisha,
                "sample_cash_poisha":available,"sample_shortfall_poisha":max(0,requested_cash_poisha-available),
                "real_cash_available":False,"can_authorize_handover":False,
                "simulation":True}


def default_sample_agents()->tuple[AgentListing,...]:
    return (AgentListing("sim_agent_alpha","Sample Agent Alpha","dhaka_demo",600_000,1_250_000),
            AgentListing("sim_agent_beta","Sample Agent Beta","chattogram_demo",175_000,800_000))
