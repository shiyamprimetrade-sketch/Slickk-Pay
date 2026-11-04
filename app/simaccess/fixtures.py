"""Deterministic fictional persona seed definitions without real identity data.

Fixture enrollment runs only with explicit opt-in in a local lab. Test PINs are
never shipped in the API response, and no user-provided real identity is used.
"""
from __future__ import annotations
from dataclasses import dataclass
from .errors import LabError,require
from .identity import IdentityRegistry
from .identifiers import minor_units
from .store import LabStore


@dataclass(frozen=True)
class SyntheticFixture:
    actor_id:str
    role:str
    label:str
    sample_balance_poisha:int
    sample_activity:tuple[tuple[str,int,str,str],...]=()


FIXTURES:tuple[SyntheticFixture,...]=(
    SyntheticFixture("sim_customer_alpha","customer","Sample Customer Alpha",250_000,
                     (("in",80_000,"sample_paid","Sample synthetic receipt"),
                      ("out",10_000,"sample_pending","Draft review only"))),
    SyntheticFixture("sim_customer_beta","customer","Sample Customer Beta",72_500,
                     (("in",12_500,"sample_paid","Synthetic sender sample"),)),
    SyntheticFixture("sim_agent_alpha","agent","Sample Registered Agent",1_250_000,
                     (("in",100_000,"sample_pending","Fictional agent float preview"),)),
    SyntheticFixture("sim_agent_beta","agent","Sample Agent Two",800_000),
    SyntheticFixture("sim_merchant_alpha","merchant","Sample Merchant Alpha",420_000,
                     (("in",42_000,"sample_paid","Sample merchant report"),)),
    SyntheticFixture("sim_operator_alpha","operator","Sample Operator",0),
)


class FixtureLoader:
    def __init__(self,store:LabStore):
        self.store=store
        self.identity=IdentityRegistry(store)

    def seed(self,*,demo_pin:str,devices:dict[str,str],allow_repeat:bool=False)->dict[str,object]:
        require(len(demo_pin)>=8,"INVALID_INPUT")
        require(isinstance(devices,dict),"INVALID_INPUT")
        created=0
        already=0
        for record in FIXTURES:
            from .identifiers import synthetic_id,device_ref
            synthetic_id(record.actor_id)
            minor_units(record.sample_balance_poisha,zero_ok=True)
            if record.actor_id not in devices:
                raise LabError("INVALID_INPUT")
            device_id=device_ref(devices[record.actor_id])
            try:
                self.identity.enroll_fixture(actor_id=record.actor_id,role=record.role,label=record.label,
                                             demo_pin=demo_pin,sample_balance_poisha=record.sample_balance_poisha)
                self.identity.enroll_device(actor_id=record.actor_id,device_id=device_id,label="Synthetic Android")
                for direction,amount,status,description in record.sample_activity:
                    self.identity.add_sample_activity(record.actor_id,direction=direction,
                                                      amount_poisha=amount,status=status,description=description)
                created+=1
            except LabError as exc:
                if exc.code=="CONFLICT" and allow_repeat:
                    already+=1
                else:
                    raise
        return {"created":created,"already_present":already,"simulation":True,
                "can_process_money":False,"personas":[{"id":f.actor_id,"role":f.role} for f in FIXTURES]}

    def status(self)->dict[str,object]:
        with self.store.read() as db:
            rows=db.execute("SELECT role,COUNT(*) AS n FROM lab_actors GROUP BY role ORDER BY role").fetchall()
        return {"roles":{r["role"]:r["n"] for r in rows},"simulation":True,
                "real_kyc_completed":False,"live_customers":0}


def sample_device_map()->dict[str,str]:
    """Only for local fixtures; do not derive real device identifiers."""
    return {f.actor_id:"sim_device_"+f.actor_id[4:]+"_fixture" for f in FIXTURES}
