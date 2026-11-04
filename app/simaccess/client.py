"""Typed synchronous localhost client for simulated customer and agent API.

This client is for integration tests and local experiments, not mobile banking.
It explicitly has no payment-posting function and refuses remote URLs.
"""
from __future__ import annotations
from dataclasses import dataclass
from urllib.parse import urlparse
import httpx
from .errors import LabError,require
from .identifiers import synthetic_id,device_ref,event_ref,minor_units


@dataclass(frozen=True)
class ClientSession:
    bearer:str
    actor_id:str
    device_id:str
    role:str
    expires_at:int
    simulation:bool=True


class LocalAccessClient:
    def __init__(self,base_url:str,*,transport:httpx.BaseTransport|None=None):
        uri=urlparse(base_url)
        if uri.scheme!="http" or uri.hostname not in ("localhost","127.0.0.1","testserver") or uri.username or uri.password or uri.fragment or uri.query:
            raise LabError("LAB_DISABLED")
        self._client=httpx.Client(base_url=base_url,transport=transport,timeout=httpx.Timeout(5.0))
        self._session:ClientSession|None=None

    def _headers(self)->dict[str,str]:
        if self._session is None:
            raise LabError("UNAUTHORIZED")
        return {"Authorization":"Bearer "+self._session.bearer,
                "X-Sim-Device":self._session.device_id}

    def request(self,method:str,path:str,*,payload:dict[str,object]|None=None,
                authenticated:bool=True)->dict[str,object]:
        require(method in ("GET","POST") and path.startswith("/lab/v4/") and "?" not in path and ".." not in path,"INVALID_INPUT")
        headers=self._headers() if authenticated else {}
        response=self._client.request(method,path,headers=headers,json=payload if method=="POST" else None)
        try:
            data=response.json()
        except ValueError as exc:
            raise LabError("INVALID_INPUT") from exc
        if not isinstance(data,dict):
            raise LabError("INVALID_INPUT")
        if response.status_code>=400:
            failure=data.get("error", "INVALID_INPUT")
            if failure not in __import__("app.simaccess.errors",fromlist=["FAILURES"]).FAILURES:
                failure="INVALID_INPUT"
            raise LabError(failure)
        if data.get("simulation") is not True:
            raise LabError("AUDIT_INTEGRITY")
        return data

    def login(self,*,actor_id:str,device_id:str,demo_pin:str)->ClientSession:
        synthetic_id(actor_id)
        device_ref(device_id)
        data=self.request("POST","/lab/v4/session",payload={"actor_id":actor_id,
                          "device_id":device_id,"demo_pin":demo_pin},authenticated=False)
        if data.get("actor")!=actor_id or data.get("real_money") is not False:
            raise LabError("AUDIT_INTEGRITY")
        value=ClientSession(data["token"],actor_id,device_id,data["role"],data["expires_at"])
        self._session=value
        return value

    def me(self)->dict[str,object]:
        return self.request("GET","/lab/v4/me")

    def activity(self)->dict[str,object]:
        return self.request("GET","/lab/v4/activity")

    def quote(self,*,operation:str,counterpart_id:str,principal_poisha:int,ref:str)->dict[str,object]:
        synthetic_id(counterpart_id)
        minor_units(principal_poisha)
        event_ref(ref)
        data=self.request("POST","/lab/v4/quotes",payload={"operation":operation,
                            "counterpart_id":counterpart_id,"principal_poisha":principal_poisha,"source_ref":ref})
        if data.get("can_execute") is not False or data.get("simulation") is not True:
            raise LabError("AUDIT_INTEGRITY")
        return data

    def review(self,quote_id:str)->dict[str,object]:
        synthetic_id(quote_id)
        data=self.request("POST",f"/lab/v4/quotes/{quote_id}/review",
                          payload={"explicit_preview_consent":True})
        if data.get("financial_posting") is not False:
            raise LabError("AUDIT_INTEGRITY")
        return data

    def cancel_request(self,request_id:str)->dict[str,object]:
        synthetic_id(request_id)
        return self.request("POST",f"/lab/v4/requests/{request_id}/cancel")

    def receipt(self,request_id:str)->dict[str,object]:
        synthetic_id(request_id)
        value=self.request("GET",f"/lab/v4/requests/{request_id}/receipt")
        if value.get("payment_proof") is not False or value.get("bank_settlement_proof") is not False:
            raise LabError("AUDIT_INTEGRITY")
        return value

    def logout(self)->bool:
        if self._session is None:
            return False
        result=self.request("POST","/lab/v4/logout")
        self._session=None
        return result.get("logged_out") is True

    def cannot_transfer(self,*_:object,**__:object)->None:
        raise LabError("SERVER_AUTHORITY_ABSENT")

    def close(self)->None:
        self._session=None
        self._client.close()

    def __enter__(self)->"LocalAccessClient":
        return self

    def __exit__(self,*_:object)->None:
        self.close()
