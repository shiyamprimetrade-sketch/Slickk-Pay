"""Opt-in FastAPI fictional access endpoints, *not* part of app.live.

This app is intentionally limited to localhost clients and fixture-only actors.
It never issues account credits, deposits, loans or financial approvals.
"""
from __future__ import annotations
import os
from dataclasses import asdict
from fastapi import FastAPI,Header,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,ConfigDict,Field
from .errors import LabError
from .service import AccessLab
from .store import assert_lab_environment


class StrictRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")


class LoginRequest(StrictRequest):
    actor_id:str=Field(min_length=8,max_length=90)
    device_id:str=Field(min_length=15,max_length=90)
    demo_pin:str=Field(min_length=8,max_length=128)


class QuoteRequest(StrictRequest):
    operation:str
    counterpart_id:str
    principal_poisha:int=Field(gt=0,le=50_000_000)
    source_ref:str
    lifetime_seconds:int=Field(default=180,ge=30,le=600)


class ReviewRequest(StrictRequest):
    explicit_preview_consent:bool


class CashUpdate(StrictRequest):
    cash_available:bool|None=None
    customer_present:bool|None=None
    warnings_acknowledged:bool|None=None


class SupportRequest(StrictRequest):
    category:str
    description:str=Field(min_length=10,max_length=500)


class QrRequest(StrictRequest):
    recipient_id:str
    operation:str
    amount_poisha:int=Field(gt=0,le=50_000_000)
    lifetime:int=Field(default=120,ge=30,le=300)


class QrPreviewRequest(StrictRequest):
    uri:str=Field(min_length=15,max_length=3000)


def create_local_access_app(lab:AccessLab,*,explicitly_opted_in:bool)->FastAPI:
    assert_lab_environment()
    if not explicitly_opted_in or os.environ.get("SLICKK_SIM_ACCESS_ENABLED")!="true":
        raise LabError("LAB_DISABLED")
    api=FastAPI(title="Slickk Pay fictional customer-agent access lab",
                version="cycle004-lab-only",docs_url=None,redoc_url=None)

    @api.exception_handler(LabError)
    async def handle_lab_error(_request:Request,exc:LabError):
        return JSONResponse(exc.public(),status_code=exc.status)

    @api.middleware("http")
    async def boundary(request:Request,call_next):
        assert_lab_environment()
        # Remote IPs are denied even if a reverse proxy changes the Host header.
        source=request.client.host if request.client else "unknown"
        if source not in ("testclient","127.0.0.1","::1","localhost"):
            return JSONResponse({"error":"LAB_DISABLED","simulation":True},status_code=403)
        if request.method not in ("GET","POST"):
            return JSONResponse({"error":"INVALID_INPUT","simulation":True},status_code=405)
        length=request.headers.get("content-length")
        if length and (not length.isdigit() or int(length)>16384):
            return JSONResponse({"error":"INVALID_INPUT","simulation":True},status_code=413)
        response=await call_next(request)
        response.headers.update({"Cache-Control":"no-store","Pragma":"no-cache",
                                 "X-Content-Type-Options":"nosniff",
                                 "X-Frame-Options":"DENY",
                                 "Referrer-Policy":"no-referrer",
                                 "Content-Security-Policy":"default-src 'none'"})
        return response

    def session(authorization:str|None,device:str|None):
        if not authorization or not authorization.startswith("Bearer ") or not device:
            raise LabError("UNAUTHORIZED")
        return lab.context(bearer=authorization[7:],device_id=device)

    def use(authorization:str|None,device:str|None):
        return session(authorization,device)

    @api.get("/lab/v4/health")
    def health():
        return lab.full_health()

    @api.get("/lab/v4/capabilities")
    def capabilities():
        return lab.capabilities.public()

    @api.get("/lab/v4/contracts")
    def contracts():
        return lab.versions.manifest()

    @api.post("/lab/v4/session")
    def login(body:LoginRequest):
        result=lab.sessions.login(actor_id=body.actor_id,device_id=body.device_id,demo_pin=body.demo_pin)
        return {"token":result.bearer,"actor":result.actor_id,"role":result.role,
                "expires_at":result.expires_at,"simulation":True,"real_money":False}

    @api.get("/lab/v4/me")
    def me(authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        ctx=use(authorization,x_sim_device)
        return lab.summary(ctx)

    @api.post("/lab/v4/logout")
    def logout(authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        ctx=use(authorization,x_sim_device)
        return {"logged_out":lab.sessions.logout(bearer=authorization[7:],device_id=x_sim_device),"simulation":True}

    @api.get("/lab/v4/activity")
    def activity(limit:int=40,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        ctx=use(authorization,x_sim_device)
        lab.policy.require(ctx,"statement:read",resource_owner=ctx.actor_id)
        return {"rows":lab.identity.sample_statement(ctx.actor_id,limit=limit),"simulation":True}

    @api.get("/lab/v4/agents")
    def agents(region:str|None=None,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.directory.search(use(authorization,x_sim_device),region=region)

    @api.get("/lab/v4/activity/search")
    def search_activity(limit:int=20,direction:str|None=None,status:str|None=None,
                        authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        from .search import ActivityQuery
        return lab.search.execute(use(authorization,x_sim_device),ActivityQuery(limit,direction,status)).public()

    @api.post("/lab/v4/quotes")
    def create_quote(body:QuoteRequest,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        ctx=use(authorization,x_sim_device)
        return lab.quotes.quote(context=ctx,**body.model_dump()).public()

    @api.get("/lab/v4/quotes")
    def quotes(limit:int=30,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        ctx=use(authorization,x_sim_device)
        return {"items":[x.public() for x in lab.quotes.list(ctx,limit=limit)],"simulation":True}

    @api.get("/lab/v4/quotes/{quote_id}")
    def quote_detail(quote_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.quotes.get(use(authorization,x_sim_device),quote_id).public()

    @api.post("/lab/v4/quotes/{quote_id}/review")
    def review(quote_id:str,body:ReviewRequest,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.requests.review(use(authorization,x_sim_device),quote_id,**body.model_dump()).public()

    @api.post("/lab/v4/quotes/{quote_id}/cancel")
    def quote_cancel(quote_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.quotes.cancel(use(authorization,x_sim_device),quote_id).public()

    @api.get("/lab/v4/requests")
    def requests(limit:int=50,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return {"items":[x.public() for x in lab.requests.list(use(authorization,x_sim_device),limit)],"simulation":True}

    @api.get("/lab/v4/requests/{request_id}")
    def request_detail(request_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.requests.get(use(authorization,x_sim_device),request_id).public()

    @api.post("/lab/v4/requests/{request_id}/cancel")
    def request_cancel(request_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.requests.cancel(use(authorization,x_sim_device),request_id).public()

    @api.get("/lab/v4/requests/{request_id}/receipt")
    def receipt(request_id:str,locale:str="en",authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.receipts.for_request(use(authorization,x_sim_device),request_id,locale).public()

    @api.post("/lab/v4/requests/{request_id}/cash-checklist")
    def create_checklist(request_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.cash.create(use(authorization,x_sim_device),request_id=request_id).public()

    @api.post("/lab/v4/requests/{request_id}/cash-checklist/update")
    def update_checklist(request_id:str,body:CashUpdate,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.cash.update(use(authorization,x_sim_device),request_id=request_id,**body.model_dump()).public()

    @api.post("/lab/v4/requests/{request_id}/cash-dialogue")
    def start_cash_dialogue(request_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.cash_dialogue.start(use(authorization,x_sim_device),request_id).public()

    @api.get("/lab/v4/requests/{request_id}/cash-dialogue")
    def get_cash_dialogue(request_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.cash_dialogue.get(use(authorization,x_sim_device),request_id).public()

    @api.post("/lab/v4/requests/{request_id}/cash-dialogue/ack")
    def cash_dialogue_ack(request_id:str,body:dict[str,str],authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        if set(body)!={"review_reference"}:
            raise LabError("INVALID_INPUT")
        return lab.cash_dialogue.acknowledge(use(authorization,x_sim_device),request_id,review_reference=body["review_reference"]).public()

    @api.post("/lab/v4/requests/{request_id}/cash-dialogue/cancel")
    def cash_dialogue_cancel(request_id:str,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.cash_dialogue.cancel(use(authorization,x_sim_device),request_id).public()

    @api.post("/lab/v4/support")
    def support(body:SupportRequest,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.support.create_draft(use(authorization,x_sim_device),**body.model_dump()).public()

    @api.get("/lab/v4/support")
    def support_list(authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return {"cases":[x.public() for x in lab.support.list(use(authorization,x_sim_device))],"simulation":True}

    @api.post("/lab/v4/qr")
    def qr_issue(body:QrRequest,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        if lab.qr is None:
            raise LabError("LAB_DISABLED")
        uri=lab.qr.issue(use(authorization,x_sim_device),**body.model_dump())
        return {"uri":uri,"simulation":True,"can_pay":False}

    @api.post("/lab/v4/qr/inspect")
    def qr_inspect(body:QrPreviewRequest,authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        if lab.qr is None:
            raise LabError("LAB_DISABLED")
        return lab.qr.inspect(use(authorization,x_sim_device),body.uri).public()

    @api.get("/lab/v4/notifications")
    def notices(authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return {"items":[x.public() for x in lab.notifications.list_for(use(authorization,x_sim_device))],"simulation":True}

    @api.get("/lab/v4/operator/metrics")
    def metrics(authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.reports.synthetic_kpi(use(authorization,x_sim_device))

    @api.get("/lab/v4/audit-proof")
    def audit_proof(authorization:str|None=Header(default=None),x_sim_device:str|None=Header(default=None)):
        return lab.operator_proof(use(authorization,x_sim_device))

    return api
