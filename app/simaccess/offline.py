"""Mobile offline and network-recovery behavior with zero financial replay.

This domain contract can be mirrored by a future React Native client. It
rejects offline write commands, stale authorization and optimistic balance
updates even when a request was previously displayed or reviewed.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require

READ_ONLY_ACTIONS=frozenset({"profile_view","sample_statement","sample_receipt","sample_agent_list",
                             "public_fees","local_support_draft","preferences"})
SERVER_READ_ACTIONS=frozenset({"profile_refresh","history_refresh","notifications_refresh"})
SERVER_PREVIEW_ACTIONS=frozenset({"quote_create","quote_review","quote_cancel","request_cancel",
                                 "qr_preview","support_save","cash_checklist"})
FORBIDDEN_ACTIONS=frozenset({"money_send","money_receive","cash_disburse","merchant_capture",
                             "loan_issue","wallet_credit","offline_transfer","bank_settle"})


@dataclass(frozen=True)
class NetworkState:
    online:bool
    session_valid:bool
    ui_in_foreground:bool
    last_verified_at:int|None
    now:int
    clock_trusted:bool
    consent_banner_seen:bool

    def __post_init__(self)->None:
        require(type(self.now) is int and self.now>0,"INVALID_INPUT")
        if self.last_verified_at is not None:
            require(type(self.last_verified_at) is int and self.last_verified_at>0,"INVALID_INPUT")


@dataclass(frozen=True)
class OfflineDecision:
    action:str
    allowed:bool
    source:str
    must_revalidate:bool
    may_mutate_balance:bool=False
    can_finish_payment:bool=False
    simulation:bool=True

    def public(self)->dict[str,object]:
        return dict(self.__dict__)


class OfflineContract:
    def __init__(self,*,cached_data_max_age:int=300):
        require(type(cached_data_max_age) is int and 0<=cached_data_max_age<=3600,"INVALID_INPUT")
        self.max_age=cached_data_max_age

    def evaluate(self,action:str,state:NetworkState)->OfflineDecision:
        require(isinstance(action,str) and action and len(action)<=60,"INVALID_INPUT")
        require(isinstance(state,NetworkState),"INVALID_INPUT")
        if action in FORBIDDEN_ACTIONS:
            return OfflineDecision(action,False,"NEVER_SUPPORTED",True)
        if action not in READ_ONLY_ACTIONS|SERVER_READ_ACTIONS|SERVER_PREVIEW_ACTIONS:
            return OfflineDecision(action,False,"UNKNOWN_ACTION",True)
        if not state.ui_in_foreground or not state.consent_banner_seen:
            return OfflineDecision(action,False,"UI_NOT_READY",True)
        if action in READ_ONLY_ACTIONS:
            if action=="public_fees" or action=="preferences":
                return OfflineDecision(action,True,"LOCAL_PUBLIC_FIXTURE",False)
            age=state.now-(state.last_verified_at or 0)
            cached=state.last_verified_at is not None and 0<=age<=self.max_age
            allowed=cached and state.session_valid and state.clock_trusted
            return OfflineDecision(action,allowed,"STALE_SAMPLE_CACHE" if allowed else "CACHE_UNVERIFIED",True)
        if not state.online or not state.clock_trusted or not state.session_valid:
            return OfflineDecision(action,False,"SERVER_UNAVAILABLE",True)
        if action in SERVER_READ_ACTIONS:
            return OfflineDecision(action,True,"SERVER_READ_REQUIRED",True)
        # Only demo preview mutations on the authenticated server; no money moves.
        return OfflineDecision(action,True,"SERVER_PREVIEW_ONLY",True)

    def assert_permitted(self,action:str,state:NetworkState)->OfflineDecision:
        decision=self.evaluate(action,state)
        if not decision.allowed:
            raise LabError("SERVER_AUTHORITY_ABSENT" if action in FORBIDDEN_ACTIONS else "ROLE_FORBIDDEN")
        return decision

    def recover_after_disconnect(self,state:NetworkState)->dict[str,object]:
        return {"clear_pending_payment_commands":True,"clear_session_token_from_shared_ui":True,
                "require_reauthentication":True,"require_server_status_refresh":True,
                "preserve_only_unsent_support_drafts":True,"pending_money_replay_queue":False,
                "simulation":True,"network_online":state.online}
