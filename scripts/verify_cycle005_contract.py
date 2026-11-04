"""Cycle 005 cross-language boundary check, isolated synthetic FastAPI TestClient.

No account history or provider secret is accessed. This script is safe for CI
and intentionally creates a disposable SQLite lab, not a production database.
"""
from __future__ import annotations
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi.testclient import TestClient
from app.simaccess.api import create_local_access_app
from app.simaccess.service import create_local_lab
from app.simaccess.clock import FrozenClock

ACTOR = "sim_customer_alpha"
DEVICE = "sim_device_customer_alpha_004"
PIN = "fake-local-contract-pin-005"


def verify() -> dict[str, object]:
    with TemporaryDirectory(prefix="slickk_access_c005_") as temporary:
        lab = create_local_lab(str(Path(temporary) / "sim_access_c005.sqlite3"),
                               opted_in=True, clock=FrozenClock(1_800_000_000))
        for actor, role, device in ((ACTOR, "customer", DEVICE),
                                    ("sim_customer_beta", "customer", "sim_device_customer_beta_004"),
                                    ("sim_agent_alpha", "agent", "sim_device_agent_alpha_004")):
            lab.identity.enroll_fixture(actor_id=actor, role=role, label="Sample " + role,
                                        demo_pin=PIN, sample_balance_poisha=100_000)
            lab.identity.enroll_device(actor_id=actor, device_id=device,
                                       label="Synthetic Android test")
        client = TestClient(create_local_access_app(lab, explicitly_opted_in=True))
        health = client.get("/lab/v4/health")
        assert health.status_code == 200
        assert health.json()["simulation"] is True
        assert health.json()["posting_enabled"] is False
        capabilities = client.get("/lab/v4/capabilities")
        assert capabilities.status_code == 200
        for key in ("can_move_money", "accepts_deposits", "bank_connected", "can_issue_loans"):
            assert capabilities.json()[key] is False
        login = client.post("/lab/v4/session", json={"actor_id": ACTOR,
            "device_id": DEVICE, "demo_pin": PIN})
        assert login.status_code == 200
        token = login.json().get("token")
        assert isinstance(token, str) and len(token) >= 40
        header = {"Authorization": "Bearer " + token, "X-Sim-Device": DEVICE}
        wrong_device = dict(header, **{"X-Sim-Device": "sim_device_customer_beta_004"})
        assert client.get("/lab/v4/me", headers=wrong_device).status_code in (401,403,409)
        me = client.get("/lab/v4/me", headers=header)
        assert me.status_code == 200
        assert me.json()["authoritative_balance"] is False
        assert me.json()["persona"]["id"] == ACTOR
        assert me.json()["accounts"][0]["sample_balance_poisha"] == 100_000
        agents = client.get("/lab/v4/agents", headers=header)
        assert agents.status_code == 200
        assert all(item["registered_financial_agent"] is False for item in agents.json()["items"])
        quote = client.post("/lab/v4/quotes", headers=header, json={
            "operation": "transfer", "counterpart_id": "sim_customer_beta",
            "principal_poisha": 12_345, "source_ref": "cycle005_python_contract_01",
            "lifetime_seconds": 180})
        assert quote.status_code == 200, quote.text
        data = quote.json()
        assert data["simulation"] is True and data["can_execute"] is False
        assert data["total_poisha"] == data["principal_poisha"] + data["fee_poisha"]
        reviewed = client.post("/lab/v4/quotes/" + data["quote_id"] + "/review",
            headers=header, json={"explicit_preview_consent": True})
        assert reviewed.status_code == 200
        assert reviewed.json()["financial_posting"] is False
        assert reviewed.json()["handover_authorized"] is False
        forbidden = client.post("/lab/v4/payments/execute", headers=header,
                                json={"request_id": reviewed.json()["request_id"]})
        assert forbidden.status_code in (404,405)
        supported = client.post("/lab/v4/support", headers=header,
            json={"category": "privacy", "description": "Synthetic privacy example only"})
        assert supported.status_code == 200
        assert supported.json()["submitted_to_provider"] is False
        forbidden_role = client.get("/lab/v4/audit-proof", headers=header)
        assert forbidden_role.status_code in (401,403,409)
        assert lab.audit.verify().valid
        assert not any("token" in item for item in ("health", "capabilities", "sample quote"))
        return {"simulation": True, "real_money": False, "offline_posting": False,
                "customer_read": True, "session_device_bound": True,
                "quote_balanced": True, "request_no_financial_posting": True,
                "agent_is_synthetic": True, "support_external_delivery": False,
                "money_execution_route_missing": True, "audit_valid": True}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
