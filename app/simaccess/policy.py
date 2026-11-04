"""Role and resource policies for a non-settling customer/agent interface."""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError, require
from .identifiers import synthetic_id
from .sessions import SessionContext

POLICY: dict[str, frozenset[str]] = {
    "customer": frozenset({"profile:read","balance:read","statement:read","quote:create",
                           "quote:review","quote:cancel","request:read","request:cancel",
                           "receipt:read","support:create","support:read","qr:issue","qr:consume"}),
    "agent": frozenset({"profile:read","balance:read","statement:read","quote:create",
                        "quote:review","quote:cancel","request:read","request:cancel",
                        "receipt:read","support:create","support:read","cash:checklist",
                        "qr:consume","agent:read"}),
    "merchant": frozenset({"profile:read","balance:read","statement:read","quote:create",
                           "quote:review","quote:cancel","request:read","request:cancel",
                           "receipt:read","support:create","support:read","qr:issue"}),
    "operator": frozenset({"profile:read","audit:read","support:read","health:read"}),
}
FORBIDDEN_CAPABILITIES = frozenset({"ledger:post","credit:issue","deposit:take",
                                   "real_cash:confirm","bank:settle","wallet:credit"})


@dataclass(frozen=True)
class AuthorizationDecision:
    actor: str
    role: str
    action: str
    allowed: bool
    resource_owner: str | None
    reason: str
    simulation: bool = True


class AccessPolicy:
    @staticmethod
    def decide(context: SessionContext, action: str, *, resource_owner: str | None = None) -> AuthorizationDecision:
        require(isinstance(action,str) and 3<=len(action)<=64,"INVALID_INPUT")
        if action in FORBIDDEN_CAPABILITIES:
            return AuthorizationDecision(context.actor_id,context.role,action,False,resource_owner,"NO_FINANCIAL_POSTING")
        authorized=action in POLICY.get(context.role,frozenset())
        if resource_owner is not None:
            synthetic_id(resource_owner)
            # Operator can view only aggregate evidence, never arbitrary private personas.
            authorized=authorized and context.actor_id==resource_owner
        return AuthorizationDecision(context.actor_id,context.role,action,authorized,resource_owner,
                                     "ALLOWED" if authorized else "ROLE_FORBIDDEN")

    @classmethod
    def require(cls, context: SessionContext, action: str,
                *, resource_owner: str | None = None) -> AuthorizationDecision:
        decision=cls.decide(context,action,resource_owner=resource_owner)
        if not decision.allowed:
            raise LabError("SERVER_AUTHORITY_ABSENT" if action in FORBIDDEN_CAPABILITIES else "ROLE_FORBIDDEN")
        return decision

    @staticmethod
    def explain(role: str) -> dict[str, object]:
        require(role in POLICY,"INVALID_INPUT")
        return {"role":role,"read_and_preview_scopes":sorted(POLICY[role]),
                "financial_posting":False,"live_settlement":False,"simulation":True}

    @staticmethod
    def assert_no_money_posting() -> bool:
        for permissions in POLICY.values():
            if permissions & FORBIDDEN_CAPABILITIES:
                raise LabError("AUDIT_INTEGRITY")
        return True
