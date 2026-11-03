"""Domain errors carry stable codes without leaking account data or credentials."""
from __future__ import annotations


class BankingError(Exception):
    code = "SANDBOX_OPERATION_REJECTED"
    retryable = False

    def __init__(self, message: str | None = None):
        super().__init__(message or self.code)

    def public(self) -> dict[str, object]:
        return {"code": self.code, "retryable": self.retryable, "simulation": True}


class InvalidValue(BankingError):
    code = "INVALID_SANDBOX_VALUE"


class Conflict(BankingError):
    code = "SANDBOX_IDEMPOTENCY_CONFLICT"


class InvariantError(BankingError):
    code = "SANDBOX_LEDGER_INVARIANT"


class InsufficientBalance(BankingError):
    code = "INSUFFICIENT_FICTIONAL_BALANCE"


class AuthorizationError(BankingError):
    code = "SANDBOX_AUTHORIZATION_REQUIRED"


class FrozenAccount(BankingError):
    code = "SANDBOX_ACCOUNT_FROZEN"


class MissingRecord(BankingError):
    code = "SANDBOX_RECORD_NOT_FOUND"


class StateError(BankingError):
    code = "SANDBOX_STATE_TRANSITION_DENIED"


class LiquidityError(BankingError):
    code = "INSUFFICIENT_SIMULATED_CASH"


class RateLimit(BankingError):
    code = "SANDBOX_VELOCITY_LIMIT"


class TransientStorage(BankingError):
    code = "SANDBOX_STORAGE_TRANSIENT"
    retryable = True


class UnauthorizedEnvironment(BankingError):
    code = "SANDBOX_ENVIRONMENT_REJECTED"


class ReportMismatch(BankingError):
    code = "SANDBOX_RECONCILIATION_MISMATCH"
