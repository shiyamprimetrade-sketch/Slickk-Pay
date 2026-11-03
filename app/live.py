"""Slickk Pay merchant checkout gateway, isolated from the fictional-wallet sandbox.

A licensed payment gateway processes all funds. This service NEVER holds funds,
issues e-money, credits simulated wallets, or grants loans. OFF by default.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import hashlib
import hmac
import json
import os
import re
from urllib.parse import urlparse
from uuid import uuid4
from typing import Callable

import httpx
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, Text, DateTime, ForeignKey, Index, select, func
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.exc import IntegrityError

from .core import taka_to_poisha, display_amount, DomainError
from .contracts import parse_provider_form, InvalidProviderForm, financial_capabilities, merchant_order_signature_valid


class Base(DeclarativeBase):
    pass


def _database_url(raw: str) -> URL:
    """Accept Render's standard PostgreSQL connectionString without logging secrets.

    SQLAlchemy 2 needs an explicit psycopg driver for Render's `postgresql://` URL.
    The URL object is passed to the engine directly, avoiding masked-password bugs.
    """
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]
    try:
        parsed = make_url(raw)
    except Exception as exc:
        raise ValueError("Invalid DATABASE_URL") from exc
    if parsed.drivername == "postgresql":
        return parsed.set(drivername="postgresql+psycopg")
    return parsed


def _read_gateway_password() -> str:
    """Read either gateway password alias; reject conflicting values without logging secrets."""
    preferred = os.getenv("SSLCOMMERZ_STORE_PASSWD")
    legacy = os.getenv("SSLCOMMERZ_STORE_PASSWORD")
    if preferred is not None and legacy is not None and preferred != legacy:
        raise ValueError("Conflicting SSLCOMMERZ password environment variables")
    return preferred if preferred is not None else (legacy or "")


def _read_live_flag() -> bool:
    """Require explicit production routing. Never infer live payments from alias alone."""
    configured = os.getenv("SLICKK_GATEWAY_LIVE", "false").strip().lower()
    if configured not in ("true", "false"):
        raise ValueError("SLICKK_GATEWAY_LIVE must be true or false")
    sandbox = os.getenv("SSLCOMMERZ_IS_SANDBOX")
    if sandbox is not None:
        sandbox = sandbox.strip().lower()
        if sandbox not in ("true", "false"):
            raise ValueError("SSLCOMMERZ_IS_SANDBOX must be true or false")
        if sandbox == configured:
            raise ValueError("Contradictory gateway sandbox and live mode settings")
        if sandbox == "false" and "SLICKK_GATEWAY_LIVE" not in os.environ:
            raise ValueError("Explicit SLICKK_GATEWAY_LIVE is required for production routing")
    return configured == "true"


class Checkout(Base):
    __tablename__ = "merchant_checkouts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    amount_poisha: Mapped[int] = mapped_column(Integer, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="initiating")
    gateway_url: Mapped[str | None] = mapped_column(Text)
    session_key: Mapped[str | None] = mapped_column(String(120))
    val_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    bank_tran_id: Mapped[str | None] = mapped_column(String(120), unique=True)
    failure_code: Mapped[str | None] = mapped_column(String(60))
    gateway_reported_net_poisha: Mapped[int | None] = mapped_column(Integer, nullable=True)


class IPNSecurityEvent(Base):
    """Minimal durable metadata for blocked IPN attempts, never raw payload/PII."""
    __tablename__ = "merchant_checkout_ipn_security_events"
    event_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    checkout_id: Mapped[str] = mapped_column(String(32), ForeignKey("merchant_checkouts.id"), nullable=False)
    existing_state: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(48), nullable=False)
    status_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    val_id_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[object] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (Index("idx_slickk_ipn_security_checkout_time", "checkout_id", "recorded_at"),)


_FINAL_STATES = frozenset({"paid", "risk_review", "failed", "cancelled", "refunded", "disputed"})


def _audit_blocked_ipn(db, row: Checkout, *, status: str, val_id: str, reason: str) -> None:
    """Persist minimal evidence while never storing raw provider IDs or body fields."""
    db.add(IPNSecurityEvent(
        event_id=uuid4().hex, checkout_id=row.id, existing_state=row.state,
        reason=reason,
        status_hint=status if status in ("VALID", "VALIDATED", "FAILED", "CANCELLED") else "OTHER",
        val_id_digest=hashlib.sha256(val_id.encode("utf-8")).hexdigest() if val_id else None,
    ))


@dataclass(frozen=True)
class Config:
    environment: str = "staging"  # staging or production
    enabled: bool = False
    gateway_live: bool = False
    regulatory_confirmation: bool = False
    api_key: str = ""
    require_signed_orders: bool = False
    order_signing_secret: str = ""
    gateway_store_id: str = ""
    gateway_store_password: str = ""
    public_base_url: str = "http://localhost:8000"
    callback_prefix: str = "/v1/gateway"
    database_url: str = "sqlite+pysqlite:///:memory:"

    @classmethod
    def from_env(cls):
        return cls(
            environment=os.getenv("SLICKK_ENV", "staging"),
            enabled=os.getenv("SLICKK_ENABLE_CHECKOUTS", "false").lower() == "true",
            gateway_live=_read_live_flag(),
            regulatory_confirmation=os.getenv("SLICKK_REGULATORY_SIGNOFF", "false").lower() == "true",
            api_key=os.getenv("SLICKK_MERCHANT_API_KEY", ""),
            require_signed_orders=os.getenv("SLICKK_REQUIRE_SIGNED_ORDERS", "false").lower() == "true",
            order_signing_secret=os.getenv("SLICKK_ORDER_SIGNING_SECRET", ""),
            gateway_store_id=os.getenv("SSLCOMMERZ_STORE_ID", ""),
            gateway_store_password=_read_gateway_password(),
            public_base_url=os.getenv("SLICKK_PUBLIC_BASE_URL", "http://localhost:8000"),
            callback_prefix=os.getenv("SLICKK_CALLBACK_PREFIX", "/v1/gateway"),
            database_url=os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:"),
        )

    def validate(self):
        if self.callback_prefix not in ("/v1/gateway", "/v1/payments"):
            raise ValueError("SLICKK_CALLBACK_PREFIX must use an approved path")
        if self.environment not in ("staging", "production"):
            raise ValueError("SLICKK_ENV must be staging or production")
        parsed = urlparse(self.public_base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
            raise ValueError("Invalid SLICKK_PUBLIC_BASE_URL")
        if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
            raise ValueError("Public base URL must be HTTPS")
        if self.gateway_live and (not self.enabled or self.environment != "production" or not self.regulatory_confirmation):
            raise ValueError("Live gateway requires enabled production mode and explicit regulatory signoff")
        if self.environment == "production" and self.enabled:
            if not self.regulatory_confirmation:
                raise ValueError("Production checkouts require explicit regulatory signoff")
            if _database_url(self.database_url).drivername != "postgresql+psycopg":
                raise ValueError("Production checkouts require persistent PostgreSQL")
        if self.enabled and (len(self.api_key) < 32 or "REPLACE" in self.api_key.upper() or not self.gateway_store_id or not self.gateway_store_password or "REPLACE" in self.gateway_store_id.upper() or "REPLACE" in self.gateway_store_password.upper()):
            raise ValueError("Enabled checkouts require merchant API key (32+ characters) and gateway credentials")
        if self.enabled and (self.require_signed_orders or self.environment == "production"):
            if len(self.order_signing_secret) < 32 or "REPLACE" in self.order_signing_secret.upper():
                raise ValueError("Signed orders require a separate 32+ character private signing secret")
        if self.enabled and (len(self.gateway_store_id) > 30 or len(self.gateway_store_password) > 30):
            raise ValueError("SSLCOMMERZ store credentials exceed provider field limit")
        if self.environment == "production" and self.enabled and parsed.scheme != "https":
            raise ValueError("Production requires HTTPS")

    @property
    def gateway_host(self) -> str:
        return "securepay.sslcommerz.com" if self.gateway_live else "sandbox.sslcommerz.com"

    @property
    def gateway_base(self) -> str:
        return f"https://{self.gateway_host}"

    @property
    def callback_paths(self) -> dict[str, str]:
        base = self.public_base_url.rstrip("/") + self.callback_prefix
        if self.callback_prefix == "/v1/payments":
            return {"success_url": base + "/success", "fail_url": base + "/fail",
                    "cancel_url": base + "/cancel", "ipn_url": base + "/ipn"}
        return {"success_url": base + "/return/success", "fail_url": base + "/return/fail",
                "cancel_url": base + "/return/cancel", "ipn_url": base + "/ipn"}


class CheckoutCreate(BaseModel):
    order_ref: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    amount_bdt: str
    product_name: str = Field(min_length=2, max_length=120)
    product_category: str = Field(default="general", min_length=2, max_length=50)
    customer_name: str = Field(min_length=2, max_length=50)
    customer_email: str = Field(min_length=5, max_length=50)
    customer_phone: str = Field(min_length=8, max_length=20)
    customer_address: str = Field(default="Dhaka", min_length=2, max_length=50)
    customer_city: str = Field(default="Dhaka", min_length=2, max_length=50)
    customer_postcode: str = Field(default="1000", min_length=3, max_length=20)


# Merchant checkout deliberately excludes regulated stored-value and credit.
_RESTRICTED_PRODUCT = re.compile(
    r"\b(?:wallet|e[\s-]?money|stored[\s-]?value|micro[\s-]?loan|loans?|remittance|cash[\s-]?in)\b",
    re.IGNORECASE,
)


def _merchant_product_allowed(body: CheckoutCreate) -> bool:
    return not _RESTRICTED_PRODUCT.search(body.product_name + " " + body.product_category)


def _amount(amount_bdt: str) -> int:
    try:
        minor = taka_to_poisha(amount_bdt)
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not 1000 <= minor <= 50_000_000:
        raise HTTPException(status_code=422, detail="Gateway accepts BDT 10.00–500,000.00")
    return minor


def _gateway_net_amount_plausible(value: object, gross_poisha: int) -> bool:
    """Gateway net amount check. It is not proof of actual bank settlement."""
    if value is None:
        return True
    try:
        minor = taka_to_poisha(str(value))
    except (DomainError, ValueError, TypeError):
        return False
    return 0 < minor <= gross_poisha


def _canonical_fingerprint(body: CheckoutCreate, minor: int) -> str:
    safe = body.model_dump(exclude={"amount_bdt"})
    safe["amount_poisha"] = minor
    return hashlib.sha256(json.dumps(safe, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _gateway_url_valid(url: str, host: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "https" and parsed.hostname == host
            and not parsed.username and not parsed.password
            and parsed.port in (None, 443) and not parsed.fragment
            and parsed.path.startswith("/gwprocess/"))


def _view(row: Checkout) -> dict:
    return {"transaction_id": row.id, "order_ref": row.order_ref, "amount_bdt": display_amount(row.amount_poisha),
            "currency": "BDT", "status": row.state, "gateway_url": row.gateway_url,
            "provider": "SSLCOMMERZ",
            "provider_reported_net_bdt": (display_amount(row.gateway_reported_net_poisha)
                                          if row.gateway_reported_net_poisha is not None else None)}


def _client_factory() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(12.0, connect=5.0), follow_redirects=False)


def create_app(settings: Config | None = None, *, client_factory: Callable[[], httpx.Client] = _client_factory) -> FastAPI:
    cfg = settings or Config.from_env()
    cfg.validate()
    # Fail closed for production at startup, rather than generating an ephemeral database.
    engine = create_engine(_database_url(cfg.database_url), pool_pre_ping=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    api = FastAPI(title="Slickk Pay Hosted Checkout", version="0.9.0", docs_url=None, redoc_url=None,
                  description="Merchant checkout through licensed gateway; no wallet, remittance or loan issuance")

    @api.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        if cfg.public_base_url.startswith("https://"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    def authorized(key: str | None):
        if not cfg.enabled:
            raise HTTPException(status_code=503, detail="Checkout is disabled")
        if not key or not hmac.compare_digest(key.encode(), cfg.api_key.encode()):
            raise HTTPException(status_code=401, detail="Valid merchant API key required")

    @api.get("/")
    def root():
        return {"service": "Slickk Pay Checkout", "version": "0.9.0", "wallets": "disabled", "loans": "disabled",
                "enabled": cfg.enabled, "gateway": "live" if cfg.gateway_live else "sandbox"}

    @api.get("/healthz")
    def healthz():
        return {"ok": True, "service": "checkout-api"}

    @api.get("/readyz")
    def readyz():
        if not cfg.enabled:
            raise HTTPException(status_code=503, detail="Checkout not enabled")
        with Session() as db:
            db.execute(select(Checkout.id).limit(1)).all()
        return {"ready": True, "gateway": "live" if cfg.gateway_live else "sandbox"}

    @api.post("/v1/checkouts", status_code=201)
    def initiate_checkout(body: CheckoutCreate,
                          x_slickk_api_key: str | None = Header(default=None),
                          x_slickk_order_timestamp: str | None = Header(default=None),
                          x_slickk_order_signature: str | None = Header(default=None)):
        authorized(x_slickk_api_key)
        if not _merchant_product_allowed(body):
            raise HTTPException(status_code=422, detail="Regulated wallet, credit and remittance products are not enabled for merchant checkout")
        minor = _amount(body.amount_bdt)
        if cfg.require_signed_orders or cfg.environment == "production":
            if not merchant_order_signature_valid(
                    cfg.order_signing_secret, timestamp=x_slickk_order_timestamp,
                    signature=x_slickk_order_signature, order_ref=body.order_ref,
                    amount_poisha=minor, product_name=body.product_name,
                    product_category=body.product_category):
                raise HTTPException(status_code=401, detail="Valid signed merchant order required")
        fingerprint = _canonical_fingerprint(body, minor)
        tran_id = "SP" + uuid4().hex[:26]  # <= 30 characters, per provider contract
        # Persist BEFORE invoking provider. One external order_ref maps to ONE transaction.
        try:
            with Session.begin() as db:
                existing = db.scalar(select(Checkout).where(Checkout.order_ref == body.order_ref).with_for_update())
                if existing:
                    if existing.fingerprint != fingerprint:
                        raise HTTPException(status_code=409, detail="Order reference was used for a different checkout")
                    if existing.state != "pending_payment":
                        raise HTTPException(status_code=409, detail="Checkout already exists; query order status")
                    return {**_view(existing), "gateway_environment": "live" if cfg.gateway_live else "sandbox"}
                db.add(Checkout(id=tran_id, order_ref=body.order_ref, amount_poisha=minor, fingerprint=fingerprint,
                                state="initiating"))
        except IntegrityError:
            # Racing duplicate request: unique constraint prevents a second provider initiation.
            raise HTTPException(status_code=409, detail="Concurrent order reference; query status")
        params = {
            "store_id": cfg.gateway_store_id, "store_passwd": cfg.gateway_store_password,
            "total_amount": display_amount(minor), "currency": "BDT", "tran_id": tran_id,
            **cfg.callback_paths,
            "emi_option": "0", "shipping_method": "NO", "num_of_item": "1",
            "product_name": body.product_name, "product_category": body.product_category,
            "product_profile": "general", "cus_name": body.customer_name,
            "cus_email": body.customer_email, "cus_phone": body.customer_phone,
            "cus_add1": body.customer_address, "cus_city": body.customer_city,
            "cus_postcode": body.customer_postcode, "cus_country": "Bangladesh",
        }
        try:
            with client_factory() as client:
                r = client.post(cfg.gateway_base + "/gwprocess/v4/api.php", data=params)
                r.raise_for_status()
                obj = r.json()
            url = obj.get("GatewayPageURL", "")
            if obj.get("status") != "SUCCESS" or not _gateway_url_valid(url, cfg.gateway_host):
                raise ValueError("Provider did not return an approved checkout URL")
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            # Never automatically retry an uncertain initiation; verify with provider first.
            with Session.begin() as db:
                row = db.get(Checkout, tran_id)
                if row and row.state == "initiating":
                    row.state = "initiation_unknown"
                    row.failure_code = "PROVIDER_UNAVAILABLE_OR_INVALID"
            raise HTTPException(status_code=502, detail="Gateway initiation not confirmed; reconcile before retry")
        with Session.begin() as db:
            row = db.get(Checkout, tran_id)
            if row.state == "initiating":
                row.state = "pending_payment"
                row.gateway_url = url
                row.session_key = (obj.get("sessionkey") or "")[:120]
            result = _view(row)
        return {**result, "gateway_environment": "live" if cfg.gateway_live else "sandbox"}

    @api.get("/v1/orders/{order_ref}")
    def get_order(order_ref: str, x_slickk_api_key: str | None = Header(default=None)):
        authorized(x_slickk_api_key)
        with Session() as db:
            row = db.scalar(select(Checkout).where(Checkout.order_ref == order_ref))
            if row is None:
                raise HTTPException(status_code=404, detail="Order not found")
            return {**_view(row), "gateway_environment": "live" if cfg.gateway_live else "sandbox"}

    @api.get("/v1/capabilities")
    def capabilities():
        return financial_capabilities(configured=cfg.enabled, environment=cfg.environment)

    @api.post("/v1/payments/ipn")
    @api.post("/v1/gateway/ipn")
    async def receive_ipn(request: Request):
        if not cfg.enabled:
            raise HTTPException(status_code=503, detail="Checkout is disabled")
        if request.headers.get("content-type", "").split(";")[0].lower() != "application/x-www-form-urlencoded":
            raise HTTPException(status_code=415, detail="Expected form-encoded IPN")
        raw = await request.body()
        if len(raw) > 16_384:
            raise HTTPException(status_code=413, detail="IPN too large")
        try:
            fields = parse_provider_form(raw)
        except InvalidProviderForm:
            raise HTTPException(status_code=400, detail="Invalid IPN form")
        tran_id = fields.get("tran_id", "")
        val_id = fields.get("val_id", "")
        # Callback body is untrusted: failure/cancellation cannot be asserted by a
        # browser redirect or unsigned gateway POST. Only validation can mark paid.
        if not tran_id:
            return {"accepted": True, "verified": False}
        if len(tran_id) > 30 or len(val_id) > 50:
            raise HTTPException(status_code=400, detail="Invalid identifiers")
        status = fields.get("status", "")
        with Session.begin() as db:
            row = db.get(Checkout, tran_id)
            if row is None:
                return {"accepted": True, "verified": False}
            if row.state in _FINAL_STATES:
                # Terminal state cannot be resurrected. A verified repeat IPN is
                # acknowledged only for the exact stored provider reference.
                prior_reference = (row.state in ("paid", "risk_review")
                                   and status in ("VALID", "VALIDATED")
                                   and bool(row.val_id) and bool(val_id)
                                   and hmac.compare_digest(row.val_id, val_id))
                if prior_reference:
                    return {"accepted": True, "verified": True, "status": row.state}
                _audit_blocked_ipn(db, row, status=status, val_id=val_id,
                                   reason="terminal_state_blocked" if row.state in ("failed", "cancelled", "refunded", "disputed")
                                          else "terminal_reference_or_status_mismatch")
                return {"accepted": True, "verified": False}
            if status not in ("VALID", "VALIDATED") or not val_id:
                return {"accepted": True, "verified": False}
            expected_amount = row.amount_poisha
        try:
            with client_factory() as client:
                response = client.get(cfg.gateway_base + "/validator/api/validationserverAPI.php", params={
                    "val_id": val_id, "store_id": cfg.gateway_store_id,
                    "store_passwd": cfg.gateway_store_password, "format": "json",
                })
                response.raise_for_status()
                verified = response.json()
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=503, detail="Verification temporarily unavailable")
        try:
            amount = _amount(str(verified.get("amount", "")))
        except HTTPException:
            amount = -1
        valid = (verified.get("status") in ("VALID", "VALIDATED")
                 and verified.get("tran_id") == tran_id
                 and verified.get("val_id") == val_id
                 and verified.get("currency") == "BDT"
                 and amount == expected_amount
                 and _gateway_net_amount_plausible(verified.get("store_amount"), expected_amount)
                 and (not verified.get("store_id") or verified.get("store_id") == cfg.gateway_store_id))
        if not valid:
            # mismatch does not mutate order or mark it paid
            return {"accepted": True, "verified": False}
        risky = str(verified.get("risk_level", "unknown")) != "0"
        bank_tran_id = str(verified.get("bank_tran_id", ""))
        if not bank_tran_id or len(bank_tran_id) > 120:
            return {"accepted": True, "verified": False}
        try:
            with Session.begin() as db:
                row = db.get(Checkout, tran_id, with_for_update=True)
                if row.state in _FINAL_STATES:
                    if (row.state in ("paid", "risk_review") and row.val_id == val_id
                            and row.bank_tran_id == bank_tran_id):
                        return {"accepted": True, "verified": True, "status": row.state}
                    _audit_blocked_ipn(db, row, status=status, val_id=val_id,
                                       reason="late_terminal_state_conflict")
                    return {"accepted": True, "verified": False}
                if row.state not in ("pending_payment", "initiating", "initiation_unknown"):
                    return {"accepted": True, "verified": False}
                # Database UNIQUE constraints prevent reuse of provider references.
                other = db.scalar(select(Checkout.id).where((Checkout.val_id == val_id) | (Checkout.bank_tran_id == bank_tran_id)))
                if other:
                    raise HTTPException(status_code=409, detail="Payment provider reference already used")
                row.state = "risk_review" if risky else "paid"
                row.val_id = val_id
                row.bank_tran_id = bank_tran_id
                if verified.get("store_amount") is not None:
                    row.gateway_reported_net_poisha = taka_to_poisha(str(verified["store_amount"]))
                row.gateway_url = None
                return {"accepted": True, "verified": True, "status": row.state}
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Conflicting payment provider reference")

    @api.api_route("/v1/payments/{outcome}", methods=["GET", "POST"], response_class=HTMLResponse)
    @api.api_route("/v1/gateway/return/{outcome}", methods=["GET", "POST"], response_class=HTMLResponse)
    def payment_return(outcome: str):
        # Browser redirects CANNOT mark payments paid. Status comes from validated IPN.
        if outcome not in ("success", "fail", "cancel"):
            raise HTTPException(status_code=404)
        return "<!doctype html><html><head><meta charset='utf-8'><title>Slickk Pay</title></head><body><h1>Payment status pending verification</h1><p>Return to the merchant to check your order. Do not pay again until verified.</p></body></html>"

    return api


app = create_app()
