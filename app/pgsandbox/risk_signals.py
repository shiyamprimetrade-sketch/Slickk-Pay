"""Explainable, deterministic anomaly signals on synthetic events only.

Signals do not authorize, reverse, delay or deny a financial transaction.
There is no real consumer profiling or credit-scoring model in this module.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from sqlalchemy import select, func
from .schema import requests, journals, postings, money_events
from .store import SandboxStore
from .guard import sim_id
from .errors import InvalidValue


@dataclass(frozen=True)
class Signal:
    code: str
    subject: str
    explanation: str
    observed_count: int
    review_required: bool
    simulation: bool = True


@dataclass(frozen=True)
class RiskSummary:
    scanned_events: int
    scanned_requests: int
    signals: tuple[Signal, ...]
    manual_review_only: bool = True
    simulation: bool = True


class SyntheticRiskSignals:
    def __init__(self, store: SandboxStore, *, max_scan: int = 20000):
        if not 1 <= max_scan <= 100000:
            raise InvalidValue("Risk scan must be bounded")
        self.store=store
        self.max_scan=max_scan

    def concentration(self, *, min_repeat: int = 5) -> tuple[Signal,...]:
        if not 2<=min_repeat<=1000:
            raise InvalidValue("Invalid concentration threshold")
        with self.store.engine.connect() as db:
            rows=db.execute(select(requests.c.agent_account,requests.c.customer_account,
                            requests.c.state).limit(self.max_scan)).all()
        pairs: dict[tuple[str,str],int]=defaultdict(int)
        for agent,customer,state in rows:
            if state=="completed":
                pairs[(agent,customer)]+=1
        return tuple(Signal("REPEATED_AGENT_CUSTOMER",agent,
                            "Repeated completed cash events for one synthetic customer",
                            count,True) for (agent,_),count in sorted(pairs.items())
                     if count>=min_repeat)

    def cancellations(self, *, minimum_requests: int = 5,
                      threshold_ppm: int = 500000) -> tuple[Signal,...]:
        if not 1<=minimum_requests<=10000 or not 0<=threshold_ppm<=1_000_000:
            raise InvalidValue("Invalid cancellation policy")
        with self.store.engine.connect() as db:
            rows=db.execute(select(requests.c.agent_account,requests.c.state)
                            .limit(self.max_scan)).all()
        total: dict[str,int]=defaultdict(int)
        cancelled: dict[str,int]=defaultdict(int)
        for agent,state in rows:
            total[agent]+=1
            if state in ("cancelled","expired","disputed"):
                cancelled[agent]+=1
        return tuple(Signal("HIGH_CANCEL_RATIO",agent,
                            "Synthetic cash operations frequently do not complete",
                            cancelled[agent],True)
                     for agent in sorted(total) if total[agent]>=minimum_requests and
                     cancelled[agent]*1_000_000>=total[agent]*threshold_ppm)

    def velocity_hotspots(self, *, max_count: int = 10,
                          min_value_poisha: int = 1_000_000) -> tuple[Signal,...]:
        if not 1<=max_count<=10000 or min_value_poisha<0:
            raise InvalidValue("Invalid risk signal threshold")
        with self.store.engine.connect() as db:
            rows=db.execute(select(money_events.c.account_id,money_events.c.amount)
                            .limit(self.max_scan)).all()
        by_actor: dict[str,tuple[int,int]]={}
        for account,amount in rows:
            count,total=by_actor.get(account,(0,0))
            by_actor[account]=(count+1,total+amount)
        return tuple(Signal("TRANSFER_VELOCITY_REVIEW",account,
                            "Historical synthetic activity exceeds manual review threshold",
                            count,True) for account,(count,total) in sorted(by_actor.items())
                     if count>max_count or total>=min_value_poisha)

    def cashout_exposure(self, *, min_poisha: int=100_000) -> tuple[Signal,...]:
        if min_poisha<=0:
            raise InvalidValue("Risk exposure threshold must be positive")
        with self.store.engine.connect() as db:
            rows=db.execute(select(requests.c.agent_account,requests.c.amount,
                                   requests.c.state,requests.c.kind)
                            .limit(self.max_scan)).all()
        outstanding: dict[str,int]=defaultdict(int)
        occurrences: dict[str,int]=defaultdict(int)
        for agent,amount,state,kind in rows:
            if kind=="cash_out" and state in ("reserved","customer_confirmed"):
                outstanding[agent]+=amount
                occurrences[agent]+=1
        return tuple(Signal("OUTSTANDING_CASHOUT_EXPOSURE",agent,
                            "Pending fictional cash handover requires liquidity review",
                            occurrences[agent],True) for agent,value in sorted(outstanding.items())
                     if value>=min_poisha)

    def evaluate(self) -> RiskSummary:
        with self.store.engine.connect() as db:
            events=min(int(db.execute(select(func.count()).select_from(journals)).scalar_one()),self.max_scan)
            request_count=min(int(db.execute(select(func.count()).select_from(requests)).scalar_one()),self.max_scan)
        signals=(self.concentration()+self.cancellations()+self.velocity_hotspots()+
                 self.cashout_exposure())
        return RiskSummary(events,request_count,tuple(sorted(signals,key=lambda x:(x.code,x.subject))))

    def review_actor(self, actor_id: str) -> tuple[Signal,...]:
        sim_id(actor_id,"subject")
        return tuple(x for x in self.evaluate().signals if x.subject==actor_id)
