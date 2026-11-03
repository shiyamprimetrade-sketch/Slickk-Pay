"""Opt-in, read-only financial integrity inspection API for an isolated laboratory.

This file is intentionally NOT imported by app.live:app, Dockerfile or Render.
No HTTP route can post transactions, create accounts, grant credit, or access
real banking infrastructure. A private operator key protects read-only details.
"""
from __future__ import annotations
from dataclasses import asdict
import hmac
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from .store import SandboxStore
from .posting import LedgerService
from .audit import SecurityAudit, LedgerAuditor
from .reports import SandboxReports
from .reconciliation import ReconciliationService
from .errors import BankingError


class Readiness(BaseModel):
    simulation: bool
    ledger_backend: str
    checkouts_enabled: bool
    connected_to_external_banks: bool
    interface: str


def create_inspection_app(*, store: SandboxStore, operator_key: str,
                          explicitly_opted_in: bool) -> FastAPI:
    if not explicitly_opted_in or not isinstance(operator_key,str) or len(operator_key) < 48:
        raise ValueError("Read-only sandbox inspection requires opt-in and 48+ character private test key")
    ledger = LedgerService(store)
    audit = SecurityAudit(store)
    reports = SandboxReports(store)
    recon = ReconciliationService(ledger)
    app = FastAPI(title="Slickk Pay fictional ledger inspection",version="cycle002-sandbox-only",
                  docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def safe_headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def authorized(token: str | None) -> None:
        if not isinstance(token,str) or not hmac.compare_digest(operator_key,token):
            raise HTTPException(401,"Private sandbox inspection key required")

    def handled(fn):
        try:
            return fn()
        except BankingError as exc:
            # No raw database error, private account data, or secret can leak.
            raise HTTPException(status_code=409,detail=exc.public()) from exc

    @app.get("/sim/v2/health",response_model=Readiness)
    def health():
        return Readiness(simulation=True,ledger_backend=store.dialect,
                         checkouts_enabled=False,connected_to_external_banks=False,
                         interface="READ_ONLY")

    @app.get("/sim/v2/capabilities")
    def capabilities(x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return {"simulation":True,"features":{
            "ledger_read_only":True,"internal_reconciliation":True,
            "cash_state_inspection":True,"external_settlement":False,
            "cash_handover":False,"microcredit_live":False,
            "banks_connected":False,"customer_production_api":False}}

    @app.get("/sim/v2/proof")
    def proof(x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: asdict(ledger.verify()))

    @app.get("/sim/v2/security-proof")
    def security_proof(x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: asdict(audit.verify()))

    @app.get("/sim/v2/accounts/{account_id}")
    def account(account_id: str, x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: asdict(ledger.balance(account_id)))

    @app.get("/sim/v2/accounts/{account_id}/statement")
    def statement(account_id: str, limit: int=Query(default=100,ge=1,le=250),
                  x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: {"rows":ledger.statement(account_id,limit=limit),
                                "simulation":True})

    @app.get("/sim/v2/accounts/{account_id}/audit")
    def account_audit(account_id: str, x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: asdict(LedgerAuditor(ledger).audit_account(account_id)))

    @app.get("/sim/v2/reconciliation/{account_id}/{period}")
    def reconcile(account_id: str,period: str,
                  x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: asdict(recon.calculate(account_id,period)))

    @app.get("/sim/v2/dashboard")
    def dashboard(x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(reports.dashboard)

    @app.get("/sim/v2/agent/{agent_account}/{commission_account}")
    def agent(agent_account: str, commission_account: str,
              x_sim_operator_key: str | None=Header(default=None)):
        authorized(x_sim_operator_key)
        return handled(lambda: asdict(reports.agent_metrics(agent_account,
                                              commission_account=commission_account)))

    return app
