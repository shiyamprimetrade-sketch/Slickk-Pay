"""Versioned cash-state contracts shared by persistence and tests.

Status names describe fictional workflows; they are not provider settlement
states. Any terminal state can only be reviewed, never silently reactivated.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import InvalidValue, StateError

CASH_STATES=frozenset({"awaiting","reserved","customer_confirmed","completed",
                       "cancelled","expired","disputed"})
TERMINAL=frozenset({"completed","cancelled","expired","disputed"})

ALLOWED: dict[str|None,frozenset[str]]={
    None:frozenset({"awaiting","reserved"}),
    "awaiting":frozenset({"completed","cancelled","expired","disputed"}),
    "reserved":frozenset({"customer_confirmed","cancelled","expired","disputed"}),
    "customer_confirmed":frozenset({"completed","cancelled","expired","disputed"}),
    "completed":frozenset(),
    "cancelled":frozenset(),
    "expired":frozenset(),
    "disputed":frozenset(),
}


@dataclass(frozen=True)
class StateTransition:
    old: str | None
    new: str
    permitted: bool
    final: bool
    reason_code: str
    simulation: bool = True


def transition(old: str | None,new: str) -> StateTransition:
    if old not in ALLOWED or new not in CASH_STATES:
        raise InvalidValue("Unknown sandbox workflow state")
    permitted=new in ALLOWED[old]
    return StateTransition(old,new,permitted,new in TERMINAL,
                           "POLICY_ALLOWED" if permitted else "TERMINAL_OR_INVALID_TRANSITION")


def require_transition(old: str | None,new: str) -> None:
    outcome=transition(old,new)
    if not outcome.permitted:
        raise StateError(f"Disallowed synthetic cash state transition {old}->{new}")


def require_op(kind: str,old: str|None,new: str) -> None:
    require_transition(old,new)
    if kind not in ("cash_in","cash_out"):
        raise InvalidValue("Unknown sandbox cash kind")
    if old is None:
        if kind=="cash_in" and new!="awaiting":
            raise StateError("Cash-in must begin awaiting")
        if kind=="cash_out" and new!="reserved":
            raise StateError("Cash-out must begin reserved")
    if kind=="cash_in" and new=="customer_confirmed":
        raise StateError("Cash-in has no separate reserved approval")
    if kind=="cash_out" and old=="reserved" and new=="completed":
        raise StateError("Cash-out requires independent customer confirmation")


def chain_transitions(kind: str,states: tuple[str,...]) -> dict[str,object]:
    old: str|None=None
    for index,state in enumerate(states):
        try:
            require_op(kind,old,state)
        except (StateError,InvalidValue):
            return {"valid":False,"index":index,"offending":state,"simulation":True}
        old=state
    return {"valid":True,"index":len(states),"terminal":old in TERMINAL,
            "simulation":True}
