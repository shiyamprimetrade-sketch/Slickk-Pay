"""Synthetic customer/agent registry and sandbox-only security policies.

The registry is intentionally not KYC, does not verify government identity and must
never be used for real account enrollment or credential authentication.  No real PIN,
NID, phone number, biometric or external identity integration is present.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import re
import secrets
from typing import Iterable


class IdentityError(ValueError):
    pass


PHONE = re.compile(r"^01[3-9][0-9]{8}$")
ROLES = frozenset({"customer", "agent", "merchant", "operator", "system"})
STATES = frozenset({"pending", "sandbox_verified", "frozen", "closed"})


def normalize_bd_phone(raw: str) -> str:
    """Normalize Bangladeshi mobile format without checking ownership."""
    if not isinstance(raw, str):
        raise IdentityError("Phone must be text")
    compact = raw.replace(" ", "").replace("-", "")
    if compact.startswith("+880"):
        compact = "0" + compact[4:]
    if not PHONE.fullmatch(compact):
        raise IdentityError("Invalid Bangladesh mobile format")
    return compact


def masked_phone(phone: str) -> str:
    normalized = normalize_bd_phone(phone)
    return normalized[:3] + "****" + normalized[-4:]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Party:
    party_id: str
    role: str
    display_name: str
    phone: str
    status: str = "pending"
    location_code: str = ""
    synthetic: bool = True

    def __post_init__(self):
        if not self.synthetic or not self.party_id.startswith("sim_"):
            raise IdentityError("Only synthetic identities are permitted")
        if self.role not in ROLES or self.status not in STATES:
            raise IdentityError("Unknown role or status")
        if not (2 <= len(self.display_name) <= 90) or any(ord(c) < 32 for c in self.display_name):
            raise IdentityError("Invalid display name")
        normalize_bd_phone(self.phone)
        if len(self.location_code) > 50:
            raise IdentityError("Invalid location")

    def public(self) -> dict[str, str | bool]:
        return {"party_id": self.party_id, "role": self.role,
                "name_masked": self.display_name[:1] + "***", "phone": masked_phone(self.phone),
                "status": self.status, "synthetic": True}


@dataclass(frozen=True)
class AgentLocation:
    agent_id: str
    district_code: str
    area_label: str
    latitude: str = ""
    longitude: str = ""
    approved_for_real_cash: bool = False

    def __post_init__(self):
        if self.approved_for_real_cash:
            raise IdentityError("Real cash operating authority cannot be self-asserted")
        if not self.district_code or len(self.district_code) > 20:
            raise IdentityError("Missing district code")
        if not self.area_label or len(self.area_label) > 80:
            raise IdentityError("Invalid area")


@dataclass(frozen=True)
class Authorization:
    subject_id: str
    role: str
    scopes: frozenset[str]
    simulated: bool = True

    def permits(self, required: str, *, subject_id: str | None = None) -> bool:
        return (self.simulated and required in self.scopes
                and (subject_id is None or subject_id == self.subject_id))


@dataclass
class SyntheticRegistry:
    """In-memory fixtures are suitable only for offline scenario testing."""
    parties: dict[str, Party] = field(default_factory=dict)
    phones: dict[str, str] = field(default_factory=dict)
    locations: dict[str, AgentLocation] = field(default_factory=dict)

    def register(self, party: Party) -> None:
        phone = normalize_bd_phone(party.phone)
        if party.party_id in self.parties or phone in self.phones:
            raise IdentityError("Duplicate party or phone")
        self.parties[party.party_id] = party
        self.phones[phone] = party.party_id

    def lookup(self, party_id: str, *, required_role: str | None = None) -> Party:
        party = self.parties.get(party_id)
        if party is None or (required_role and party.role != required_role):
            raise IdentityError("Party missing or role mismatch")
        return party

    def by_phone(self, raw: str) -> Party:
        phone = normalize_bd_phone(raw)
        identity = self.phones.get(phone)
        if identity is None:
            raise IdentityError("No matching synthetic account")
        return self.parties[identity]

    def approve_sandbox(self, party_id: str) -> Party:
        from dataclasses import replace
        p = self.lookup(party_id)
        if p.status != "pending":
            raise IdentityError("Only pending synthetic accounts may be approved")
        changed = replace(p, status="sandbox_verified")
        self.parties[party_id] = changed
        return changed

    def freeze(self, party_id: str) -> Party:
        from dataclasses import replace
        p = self.lookup(party_id)
        if p.status == "closed":
            raise IdentityError("Closed party cannot be frozen")
        changed = replace(p, status="frozen")
        self.parties[party_id] = changed
        return changed

    def add_location(self, location: AgentLocation) -> None:
        agent = self.lookup(location.agent_id, required_role="agent")
        if agent.status != "sandbox_verified":
            raise IdentityError("Synthetic agent must be approved")
        self.locations[agent.party_id] = location

    def nearby_agents(self, district: str) -> list[dict[str, str | bool]]:
        output = []
        for agent_id, point in self.locations.items():
            if point.district_code == district and self.parties[agent_id].status == "sandbox_verified":
                output.append({**self.parties[agent_id].public(), "area": point.area_label})
        return output


def synthetic_customer(customer_id: str, phone: str, name: str) -> Party:
    return Party("sim_" + customer_id, "customer", name, normalize_bd_phone(phone))


def synthetic_agent(agent_id: str, phone: str, name: str) -> Party:
    return Party("sim_" + agent_id, "agent", name, normalize_bd_phone(phone))


def constant_time_token_match(raw: str, stored_digest: str) -> bool:
    """Token proof for isolated simulations; not an SMS OTP implementation."""
    return hmac.compare_digest(hashlib.sha256(raw.encode()).hexdigest(), stored_digest)


def synthetic_confirmation_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(24)
    return raw, hashlib.sha256(raw.encode()).hexdigest()
