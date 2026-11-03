"""Read-only smoke test for *disabled* Render staging checkout. No payment call."""
import json
import sys
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import urlopen


def verify(base: str):
    p = urlsplit(base)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ("", "/"):
        raise ValueError("Expected an HTTPS base URL with no extra path")
    with urlopen(base.rstrip("/") + "/healthz", timeout=12) as r:
        assert r.status == 200 and json.load(r)["ok"] is True, "Unhealthy service"
    with urlopen(base.rstrip("/") + "/", timeout=12) as r:
        state = json.load(r)
    assert state["enabled"] is False, "FAIL: checkout is unexpectedly enabled"
    assert state["gateway"] == "sandbox", "FAIL: live gateway flag detected"
    assert state["wallets"] == "disabled" and state["loans"] == "disabled", "FAIL: unapproved product active"
    try:
        urlopen(base.rstrip("/") + "/readyz", timeout=12)
    except HTTPError as exc:
        assert exc.code == 503, f"Expected disabled readiness, got {exc.code}"
    else:
        raise AssertionError("FAIL: readiness should be disabled in staging")
    print("PASS: staging service healthy, payments/loans/wallets DISABLED")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python scripts/smoke_staging.py https://<service>.onrender.com")
    verify(sys.argv[1])
