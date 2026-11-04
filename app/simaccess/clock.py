"""Injectable clock used for deterministic expiry and skew-aware verification."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from .errors import LabError, require


class Clock:
    def now(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())


class FrozenClock(Clock):
    def __init__(self, initial: int = 1_800_000_000):
        require(type(initial) is int and initial > 0, "INVALID_INPUT")
        self._time = initial
        self._lock = RLock()

    def now(self) -> int:
        with self._lock:
            return self._time

    def advance(self, seconds: int) -> int:
        require(type(seconds) is int and seconds >= 0, "INVALID_INPUT")
        with self._lock:
            self._time += seconds
            return self._time

    def set(self, moment: int) -> int:
        require(type(moment) is int and moment >= self.now(), "INVALID_INPUT")
        with self._lock:
            self._time = moment
            return self._time


@dataclass(frozen=True)
class Validity:
    issued_at: int
    expires_at: int

    def __post_init__(self) -> None:
        require(type(self.issued_at) is int and type(self.expires_at) is int, "INVALID_INPUT")
        require(self.issued_at > 0 and self.issued_at < self.expires_at, "INVALID_INPUT")

    def still_valid(self, now: int, *, tolerance: int = 0) -> bool:
        return self.issued_at - tolerance <= now < self.expires_at

    def seconds_left(self, now: int) -> int:
        return max(0, self.expires_at - now)


def assert_fresh(issued_at: int, expires_at: int, now: int, *, max_age: int = 600, leeway: int = 15) -> None:
    require(type(issued_at) is int and type(expires_at) is int, "INVALID_INPUT")
    require(0 < expires_at - issued_at <= max_age, "INVALID_INPUT")
    if issued_at > now + leeway or now >= expires_at:
        raise LabError("SESSION_EXPIRED")
