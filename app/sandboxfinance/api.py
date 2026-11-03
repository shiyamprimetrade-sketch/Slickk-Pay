"""Loopback-only sandbox API facade; never deploy as a financial service.

It is separate from app.live:app, cannot contact banking networks and requires
an explicit local simulation opt-in. Responses consistently label money as
fictional. Not a user authentication, KYC, merchant gateway or live cash API.
"""
from __future__ import annotations

from dataclasses import asdict
import os
from pathlib import Path
import secrets
from typing import Literal

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field, ConfigDict

from .identity import SyntheticRegistry, synthetic_customer, synthetic_agent, Party
from .ledger import SandboxLedger, LedgerError, InsufficientFunds, DuplicateReference
from .pricing import initial_pilot, poisha_to_bdt, bdt_to_poisha, PriceError
from .workflows import CashDesk, CustomerTransfers, prepare_synthetic_system, WorkflowError


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ParticipantCreate(Strict):
    identity: str = Field(pattern=r"^[a-z0-9_-]{4,32}$")
    role: Literal["customer", "agent"]
    name: str = Field(min_length=2, max_length=80)
    phone: str = Field(min_length=11, max_length=15)


class FundingRequest(Strict):
    account_id: str = Field(min_length=4, max_length=96)
    amount_bdt: str = Field(min_length=1, max_length=20)
    reference: str = Field(min_length=4, max_length=96)


class TransferRequest(Strict):
    sender_id: str
    recipient_id: str
    amount_bdt: str
    reference: str
    sender_confirmed: bool


class CashCreate(Strict):
    customer_id: str
    agent_id: str
    amount_bdt: str


class CashConfirm(Strict):
    agent_id: str
    token: str
    handover_confirmed: bool


class CashCancel(Strict):
    actor_id: str
    reason: str = Field(default="sandbox_cancel", min_length=4, max_length=100)


class AgentCash(Strict):
    agent_id: str
    available_bdt: str
    capacity_bdt: str


class SandboxRequestError(Exception):
    pass


def _serialize_receipt(record) -> dict:
    result = asdict(record)
    result["financial_environment"] = "fictional-sandbox"
    return result


def build_sandbox_app(*, database_path: str | Path, explicit_local_opt_in: bool,
                      control_key: str) -> FastAPI:
    if not explicit_local_opt_in or not isinstance(control_key, str) or len(control_key) < 32:
        raise ValueError("Sandbox API requires explicit opt-in and a strong locally generated key")
    if str(database_path) == ":memory:":
        raise ValueError("Sandbox API needs a named, isolated SQLite file")
    ledger = SandboxLedger(database_path)
    registry = SyntheticRegistry()
    desk = CashDesk(ledger, registry)
    transfers = CustomerTransfers(ledger, registry)
    prepare_synthetic_system(ledger, registry)
    app = FastAPI(title="Slickk Pay fictional sandbox only", version="cycle001")

    def authorize(key: str | None):
        if not key or not secrets.compare_digest(key, control_key):
            raise HTTPException(status_code=401, detail="Sandbox key required")

    def safe(call):
        try:
            return call()
        except (LedgerError, WorkflowError, PriceError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=type(exc).__name__) from exc

    @app.get("/simulation/status")
    def status():
        return {"simulation": True, "real_funds": False, "bank_connected": False,
                "loans_enabled": False, "cash_handover_real": False,
                "regulatory_authorization_asserted": False}

    @app.post("/simulation/participants", status_code=201)
    def register_participant(body: ParticipantCreate, x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        def action():
            party = (synthetic_customer(body.identity, body.phone, body.name)
                     if body.role == "customer" else synthetic_agent(body.identity, body.phone, body.name))
            registry.register(party)
            registry.approve_sandbox(party.party_id)
            prepare_synthetic_system(ledger, registry)
            return registry.lookup(party.party_id).public()
        return safe(action)

    @app.post("/simulation/fund", status_code=201)
    def fund(body: FundingRequest, x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: _serialize_receipt(ledger.synthetic_issue(body.account_id,
                     bdt_to_poisha(body.amount_bdt), reference=body.reference)))

    @app.post("/simulation/transfers", status_code=201)
    def transfer(body: TransferRequest, x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: _serialize_receipt(transfers.send(
            sender_id=body.sender_id, recipient_id=body.recipient_id,
            principal=bdt_to_poisha(body.amount_bdt), reference=body.reference,
            customer_confirmed=body.sender_confirmed)))

    @app.get("/simulation/accounts/{account_id}")
    def account(account_id: str, x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: {**asdict(ledger.account(account_id)),
                             "environment": "fictional", "balance_bdt":
                             poisha_to_bdt(ledger.account(account_id).balance_poisha)})

    @app.post("/simulation/agent/cash-declaration")
    def cash_declaration(body: AgentCash, x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        def action():
            desk.register_agent_cash(body.agent_id,
                                     reported_cash_poisha=bdt_to_poisha(body.available_bdt),
                                     limit_poisha=bdt_to_poisha(body.capacity_bdt))
            return {"simulation": True, "agent_id": body.agent_id,
                    "cash_declared": True, "physical_money_verified": False}
        return safe(action)

    @app.post("/simulation/cash/{operation}/requests", status_code=201)
    def start_cash(operation: Literal["cash_in", "cash_out"], body: CashCreate,
                   x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        def action():
            fn = desk.request_cash_in if operation == "cash_in" else desk.request_cash_out
            simulated = fn(body.customer_id, body.agent_id, bdt_to_poisha(body.amount_bdt))
            return {"request": asdict(simulated.request),
                    "test_customer_confirmation_token": simulated.customer_token,
                    "warning": simulated.warning, "simulation": True}
        return safe(action)

    @app.post("/simulation/cash/{request_id}/confirm")
    def confirm_cash(request_id: str, body: CashConfirm,
                     x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: asdict(desk.confirm(request_id, agent_id=body.agent_id,
                             customer_token=body.token,
                             cash_handover_confirmed=body.handover_confirmed)))

    @app.post("/simulation/cash/{request_id}/cancel")
    def cancel_cash(request_id: str, body: CashCancel,
                    x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: asdict(desk.cancel(request_id,
                             actor_id=body.actor_id, reason=body.reason)))

    @app.get("/simulation/cash/{request_id}/audit")
    def audit_cash(request_id: str, x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: {"simulation": True, "entries": desk.audit(request_id)})

    @app.get("/simulation/journal/verify")
    def verify(x_simulation_key: str | None = Header(default=None)):
        authorize(x_simulation_key)
        return safe(lambda: ledger.verify())

    return app


def local_only_app() -> FastAPI:
    """Factory for manual 127.0.0.1 development. No hosted default app instance."""
    if os.getenv("SLICKK_SANDBOX_LOCAL_ONLY") != "true":
        raise ValueError("Set SLICKK_SANDBOX_LOCAL_ONLY=true for explicit local trial")
    if os.getenv("SLICKK_ENV") == "production" or os.getenv("SLICKK_ENABLE_CHECKOUTS") == "true":
        raise ValueError("Financial checkout and this local simulator cannot run together")
    return build_sandbox_app(database_path=os.getenv("SLICKK_SANDBOX_DB", "./fictional-money.sqlite3"),
                             explicit_local_opt_in=True,
                             control_key=os.environ.get("SLICKK_SANDBOX_CONTROL_KEY", ""))
