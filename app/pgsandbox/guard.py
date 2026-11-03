"""Hard fail-closed routing for the *separate* PostgreSQL financial sandbox."""
from __future__ import annotations
from dataclasses import dataclass
import os
import re
from sqlalchemy.engine import make_url, URL
from .errors import UnauthorizedEnvironment, InvalidValue

_SANDBOX_NAME = "slickk_ci_test"
_SAFE_LOCAL = frozenset({"localhost", "127.0.0.1", "::1"})


def assert_sandbox_target(url: str, *, allow_local_sqlite: bool = False) -> URL:
    if not isinstance(url, str) or not url:
        raise UnauthorizedEnvironment("Missing sandbox database URL")
    try:
        parsed = make_url(url)
    except Exception as exc:
        raise UnauthorizedEnvironment("Invalid sandbox database URL") from exc
    if parsed.drivername == "sqlite+pysqlite" and allow_local_sqlite:
        database = parsed.database or ""
        if not database or database == ":memory:":
            raise UnauthorizedEnvironment("Sandbox requires a persistent temporary SQLite test file")
        if any(token in database.lower() for token in ("prod", "live", "customer", "wallet")):
            raise UnauthorizedEnvironment("Unsafe SQLite filename")
        return parsed
    if parsed.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise UnauthorizedEnvironment("Only PostgreSQL or explicit local SQLite tests")
    if os.environ.get("SLICKK_PG_SANDBOX") != "true":
        raise UnauthorizedEnvironment("Explicit sandbox switch required")
    if parsed.host not in _SAFE_LOCAL or parsed.database != _SANDBOX_NAME or parsed.port not in (None, 5432):
        raise UnauthorizedEnvironment("Refusing remote or production financial database")
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    return parsed


def sim_id(value: str, kind: str = "identifier") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"sim_[A-Za-z0-9_:.\-]{4,88}", value):
        raise InvalidValue(f"Invalid synthetic {kind}")
    return value


def event_key(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][A-Za-z0-9_:.-]{7,96}", value):
        raise InvalidValue("Invalid event reference")
    return value


def owner_key(value: str) -> str:
    return sim_id(value, "owner")


def assert_not_live_environment() -> None:
    for key in ("SLICKK_GATEWAY_LIVE", "SLICKK_REGULATORY_SIGNOFF"):
        if os.environ.get(key, "false").lower() == "true":
            raise UnauthorizedEnvironment("Sandbox finance cannot coexist with live payment mode")
    if os.environ.get("SLICKK_ENV", "staging").lower() == "production":
        raise UnauthorizedEnvironment("Sandbox finance cannot start with production environment")


@dataclass(frozen=True)
class SandboxDescriptor:
    enabled: bool
    product: str = "Slickk Pay fictional accounting lab"
    network_integrations: tuple[str, ...] = ()
    money_mode: str = "SIMULATED_ONLY"

    def __post_init__(self):
        if self.network_integrations or self.money_mode != "SIMULATED_ONLY":
            raise UnauthorizedEnvironment("No real provider connections in sandbox")

    def public(self) -> dict[str, object]:
        return {"enabled": self.enabled, "product": self.product,
                "network_integrations": [], "money_mode": self.money_mode,
                "simulation": True}
