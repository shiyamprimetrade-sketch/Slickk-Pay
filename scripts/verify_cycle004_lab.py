"""Self-contained financial-safety demonstration on a temporary SQLite lab.

No database URI, network API key, real identity, bank, payment or credit is
needed. The script deliberately fails when live-money flags are enabled.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from app.simaccess.clock import FrozenClock
from app.simaccess.crypto import KeyRing,SigningKey
from app.simaccess.service import AccessLab
from app.simaccess.store import LabStore
from app.simaccess.conformance import ConformanceSuite
from app.simaccess.consistency import ConsistencyAuditor
from app.simaccess.faults import FaultProbe
from app.simaccess.errors import LabError


def run()->dict[str,object]:
    for name in ("SLICKK_GATEWAY_LIVE","SLICKK_REGULATORY_SIGNOFF","SLICKK_ENABLE_CHECKOUTS"):
        if os.environ.get(name,"false").lower()=="true":
            raise RuntimeError("Aborting simulated access test in live money environment")
    with TemporaryDirectory(prefix="slickk_cycle004_") as tmp:
        clock=FrozenClock(1_800_000_000)
        store=LabStore(str(Path(tmp)/"sim_access_verification.sqlite3"),opted_in=True,clock=clock)
        ring=KeyRing((SigningKey("sim_key_ci_only_004",bytes(range(32)),clock.now()-100),),"sim_key_ci_only_004")
        lab=AccessLab(store,qr_keyring=ring)
        ident=lab.identity
        pin="test-only-replace-in-every-new-lab"
        people={"sim_customer_alpha":("customer","sim_device_customer_alpha_004"),
                "sim_customer_beta":("customer","sim_device_customer_beta_004"),
                "sim_agent_alpha":("agent","sim_device_agent_alpha_004")}
        for actor,(role,device) in people.items():
            ident.enroll_fixture(actor_id=actor,role=role,label="Synthetic "+role,demo_pin=pin)
            ident.enroll_device(actor_id=actor,device_id=device,label="Test-only Android")
        bearer=lab.sessions.login(actor_id="sim_customer_alpha",
                    device_id="sim_device_customer_alpha_004",demo_pin=pin)
        ctx=lab.sessions.require(bearer=bearer.bearer,device_id="sim_device_customer_alpha_004")
        quote=lab.quotes.quote(context=ctx,operation="cash_out",counterpart_id="sim_agent_alpha",
                               principal_poisha=100_000,source_ref="ci_preview_quote_001")
        review=lab.requests.review(ctx,quote.id,explicit_preview_consent=True)
        report=ConformanceSuite(lab).assert_release_safe()
        integrity=ConsistencyAuditor(store).assert_valid()
        rollback=FaultProbe(store).assert_rollback(actor_id="sim_customer_alpha",correlation="ci_fault_probe_001")
        forbidden=False
        try:
            lab.requests.attempt_execution(ctx,review.id)
        except LabError as error:
            forbidden=error.code=="SERVER_AUTHORITY_ABSENT"
        if not forbidden:
            raise RuntimeError("Sandbox attempted a forbidden financial posting")
        result={"simulation":True,"real_money":False,"external_connections":0,
                "quote_fee_poisha":quote.fee_poisha,"review_issued":review.status=="reviewed",
                "conformance_checks":len(report.checks),"conformance_passed":report.passed,
                "integrity_valid":integrity.valid,"rollback_valid":rollback.data_unchanged,
                "payment_blocked":forbidden,"audit_events":lab.audit.verify().checked}
        if not all((result["conformance_passed"],result["integrity_valid"],
                    result["rollback_valid"],result["payment_blocked"])):
            raise RuntimeError("Synthetic access integrity checks failed")
        return result


if __name__=="__main__":
    print(json.dumps(run(),sort_keys=True))
