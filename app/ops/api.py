"""Fail-closed, stateless staging previews for merchant operations evidence.

This router makes NO provider call, stores NO customer data, and authorizes NO
payment. It is off unless an explicit staging-only environment flag and a
separately configured merchant API key are both present. No production route.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hmac
import os
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field, ConfigDict

from .primitives import EvidenceError, PolicyError, parse_utc, minor_from_bdt
from .settlement import GatewayRecord, BankCredit, GatewayState, Reconciler
from .risk import RiskInput, RiskPolicy, RiskEvaluator
from .reports import VerificationGate, GateStatus, ReadinessChecklist


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GatewayPreviewRow(StrictModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    tran_id: str = Field(min_length=1, max_length=96)
    val_id: str = Field(min_length=1, max_length=96)
    bank_tran_id: str = Field(min_length=1, max_length=96)
    batch_ref: str | None = Field(default=None, max_length=96)
    gross_bdt: str = Field(max_length=24)
    net_bdt: str = Field(max_length=24)
    fee_bdt: str = Field(max_length=24)
    state: Literal["valid", "validated", "risk_review", "failed", "cancelled", "refunded", "disputed"]
    verified: bool
    risk_level: int = Field(ge=0, le=10)
    paid_at: str = Field(max_length=35)


class BankPreviewRow(StrictModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    statement_ref: str = Field(min_length=1, max_length=96)
    batch_ref: str = Field(min_length=1, max_length=96)
    amount_bdt: str = Field(max_length=24)
    posted_at: str = Field(max_length=35)
    statement_verified: bool


class ReconcilePreviewRequest(StrictModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(max_length=35)
    gateway: list[GatewayPreviewRow] = Field(max_length=100)
    bank: list[BankPreviewRow] = Field(max_length=100)
    settlement_window_days: int = Field(default=2, ge=0, le=30)


class RiskPreviewRequest(StrictModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    transaction_id: str = Field(min_length=1, max_length=96)
    order_ref: str = Field(min_length=1, max_length=96)
    amount_bdt: str = Field(max_length=24)
    created_at: str = Field(max_length=35)
    now: str = Field(max_length=35)
    gateway_verified: bool
    gateway_risk_level: int | None = Field(default=None, ge=0, le=10)
    invoice_authorized: bool = False
    prior_chargebacks: int = Field(default=0, ge=0, le=10_000)
    change_count: int = Field(default=0, ge=0, le=10_000)


class GatePreviewRow(StrictModel):
    gate_id: str = Field(min_length=1, max_length=96)
    status: Literal["passed", "failed", "pending", "not_applicable"]
    evidence_digest: str | None = Field(default=None, max_length=64)
    reviewer_ref: str | None = Field(default=None, max_length=96)


class ReadinessPreviewRequest(StrictModel):
    merchant_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(max_length=35)
    gates: list[GatePreviewRow] = Field(max_length=50)


class OpsPreviewConfig:
    """Explicit capability switch; refuse previews from production even if misconfigured."""

    def __init__(self, *, environment: str, merchant_api_key: str,
                 enabled: bool = False) -> None:
        self.environment = environment
        self.merchant_api_key = merchant_api_key
        self.enabled = enabled
        if enabled and environment != "staging":
            raise ValueError("Operations previews cannot be enabled in production")
        if enabled and (not isinstance(merchant_api_key, str) or len(merchant_api_key) < 32):
            raise ValueError("Operations previews require a private 32+ character merchant API key")

    @classmethod
    def from_env(cls, *, environment: str, merchant_api_key: str) -> "OpsPreviewConfig":
        raw = os.getenv("SLICKK_OPS_PREVIEW_ENABLED", "false").lower().strip()
        if raw not in ("true", "false"):
            raise ValueError("SLICKK_OPS_PREVIEW_ENABLED must be true or false")
        return cls(environment=environment, merchant_api_key=merchant_api_key, enabled=(raw == "true"))


def create_ops_router(config: OpsPreviewConfig) -> APIRouter:
    if not isinstance(config, OpsPreviewConfig):
        raise ValueError("Expected OpsPreviewConfig")
    router = APIRouter(tags=["offline merchant operations previews"])

    def guard(key: str | None) -> None:
        if not config.enabled:
            raise HTTPException(status_code=503, detail="Operations previews disabled")
        if not key or not hmac.compare_digest(key, config.merchant_api_key):
            raise HTTPException(status_code=401, detail="Merchant authentication required")

    @router.get("/v1/ops/contract")
    def contract():
        return {"version": "1.0", "environment": config.environment,
                "enabled": config.enabled, "features": {
                    "gateway_bank_reconciliation_preview": config.enabled,
                    "risk_triage_preview": config.enabled,
                    "readiness_evidence_preview": config.enabled,
                }, "customer_funds_movement": False, "loans": False,
                "bank_statements_independently_verified_by_api": False,
                "payment_provider_requests": False, "persistence": "none"}

    @router.post("/v1/ops/reconcile/preview")
    def reconciliation(body: ReconcilePreviewRequest,
                       x_slickk_api_key: str | None = Header(default=None)):
        guard(x_slickk_api_key)
        try:
            gateway = [GatewayRecord(
                merchant_id=r.merchant_id, tran_id=r.tran_id, val_id=r.val_id,
                bank_tran_id=r.bank_tran_id, batch_ref=r.batch_ref,
                gross_poisha=minor_from_bdt(r.gross_bdt),
                provider_net_poisha=minor_from_bdt(r.net_bdt),
                provider_fee_poisha=minor_from_bdt(r.fee_bdt, allow_zero=True),
                currency="BDT", state=GatewayState(r.state), verified=r.verified,
                risk_level=r.risk_level, paid_at=parse_utc(r.paid_at)) for r in body.gateway]
            bank = [BankCredit(
                merchant_id=r.merchant_id, statement_ref=r.statement_ref,
                batch_ref=r.batch_ref, amount_poisha=minor_from_bdt(r.amount_bdt),
                currency="BDT", posted_at=parse_utc(r.posted_at),
                bank_statement_verified=r.statement_verified) for r in body.bank]
            report = Reconciler(settlement_window_days=body.settlement_window_days).reconcile(
                merchant_id=body.merchant_id, gateway=gateway, bank=bank,
                as_of=parse_utc(body.as_of))
        except (EvidenceError, PolicyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"preview": report.as_dict(),
                "evidence_source": "operator_supplied_unverified_preview",
                "real_bank_settlement_confirmed": False,
                "financial_state_mutated": False}

    @router.post("/v1/ops/risk/preview")
    def risk(body: RiskPreviewRequest,
             x_slickk_api_key: str | None = Header(default=None)):
        guard(x_slickk_api_key)
        try:
            item = RiskInput(
                merchant_id=body.merchant_id, order_ref=body.order_ref,
                transaction_id=body.transaction_id,
                amount_poisha=minor_from_bdt(body.amount_bdt),
                created_at=parse_utc(body.created_at),
                gateway_verified=body.gateway_verified,
                gateway_risk_level=body.gateway_risk_level,
                invoice_authorized=body.invoice_authorized,
                prior_chargebacks=body.prior_chargebacks,
                change_count=body.change_count)
            assessment = RiskEvaluator().evaluate(item, RiskPolicy(body.merchant_id, version=1),
                                                  now=parse_utc(body.now), record=False)
        except (EvidenceError, PolicyError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"preview": assessment.as_dict(),
                "provider_authorization": "not_performed",
                "manual_review_required_for_approval": True,
                "financial_state_mutated": False}

    @router.post("/v1/ops/readiness/preview")
    def readiness(body: ReadinessPreviewRequest,
                  x_slickk_api_key: str | None = Header(default=None)):
        guard(x_slickk_api_key)
        try:
            gates = [VerificationGate(row.gate_id, GateStatus(row.status),
                                      row.evidence_digest, row.reviewer_ref)
                     for row in body.gates]
            checklist = ReadinessChecklist()
            result = checklist.assess(merchant_id=body.merchant_id,
                                      now=parse_utc(body.as_of), gates=gates)
        except EvidenceError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"preview": result.as_dict(), "missing_gates": checklist.missing(gates),
                "compliance_review_verified_by_api": False,
                "production_activation_performed": False}

    return router
