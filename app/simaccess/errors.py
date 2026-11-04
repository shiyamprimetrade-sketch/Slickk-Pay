"""Public, structured failures for the fictional-money access lab.

Exception messages are codes, never database, identity, or credential details.
The HTTP layer may attach a localized description, but it must not return
arbitrary nested exception causes to a remote caller.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Failure:
    code: str
    status: int
    retryable: bool = False
    label_en: str = "Request cannot be completed"
    label_bn: str = "অনুরোধটি সম্পন্ন করা যাচ্ছে না"


FAILURES: dict[str, Failure] = {
    "LAB_DISABLED": Failure("LAB_DISABLED", 503),
    "INVALID_INPUT": Failure("INVALID_INPUT", 422),
    "INVALID_AMOUNT": Failure("INVALID_AMOUNT", 422),
    "INVALID_REFERENCE": Failure("INVALID_REFERENCE", 422),
    "UNAUTHORIZED": Failure("UNAUTHORIZED", 401),
    "SESSION_EXPIRED": Failure("SESSION_EXPIRED", 401),
    "SESSION_REVOKED": Failure("SESSION_REVOKED", 401),
    "DEVICE_MISMATCH": Failure("DEVICE_MISMATCH", 401),
    "ROLE_FORBIDDEN": Failure("ROLE_FORBIDDEN", 403),
    "NOT_FOUND": Failure("NOT_FOUND", 404),
    "CONFLICT": Failure("CONFLICT", 409),
    "ALREADY_REVIEWED": Failure("ALREADY_REVIEWED", 409),
    "QUOTE_EXPIRED": Failure("QUOTE_EXPIRED", 409),
    "QUOTE_CHANGED": Failure("QUOTE_CHANGED", 409),
    "REQUEST_FINAL": Failure("REQUEST_FINAL", 409),
    "REPLAY_BLOCKED": Failure("REPLAY_BLOCKED", 409),
    "RATE_LIMIT": Failure("RATE_LIMIT", 429, retryable=True),
    "AUDIT_INTEGRITY": Failure("AUDIT_INTEGRITY", 409),
    "RECOVERY_BLOCKED": Failure("RECOVERY_BLOCKED", 409),
    "SERVER_AUTHORITY_ABSENT": Failure("SERVER_AUTHORITY_ABSENT", 403),
    "PROVIDER_ABSENT": Failure("PROVIDER_ABSENT", 503),
    "SIMULATION_ONLY": Failure("SIMULATION_ONLY", 403),
}


class LabError(Exception):
    """Known failure from a deliberately limited simulation boundary."""
    def __init__(self, code: str, *, safe_context: str = ""):
        if code not in FAILURES:
            raise ValueError("Unknown sanitized error code")
        self.failure = FAILURES[code]
        self.code = code
        self.safe_context = safe_context[:100]
        super().__init__(code)

    @property
    def status(self) -> int:
        return self.failure.status

    def public(self, locale: str = "en") -> dict[str, object]:
        return {
            "error": self.code,
            "message": self.failure.label_bn if locale == "bn" else self.failure.label_en,
            "retryable": self.failure.retryable,
            "simulation": True,
        }


def require(condition: bool, code: str) -> None:
    if not condition:
        raise LabError(code)


def deny_posting() -> None:
    """Never expose a switch that can disable this guard."""
    raise LabError("SERVER_AUTHORITY_ABSENT")
