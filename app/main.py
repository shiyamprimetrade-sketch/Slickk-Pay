"""Local-only FastAPI application. Do not publish to the Internet."""
from pathlib import Path
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .core import Store, DomainError

DB_FILE = os.environ.get("SLICKK_DB", str(Path(__file__).resolve().parents[1] / "data" / "sandbox.sqlite3"))
store = Store(DB_FILE)
app = FastAPI(title="Slickk Pay Sandbox API", version="0.1.0", description="Not a regulated banking, payment or lending service")


class TransferRequest(BaseModel):
    sender_id: str
    recipient_id: str
    amount_bdt: str
    request_id: str = Field(min_length=8, max_length=128)


class CreditQuoteRequest(BaseModel):
    borrower_id: str
    biller_id: str
    category: str
    amount_bdt: str
    term_days: int


class CreditRequest(CreditQuoteRequest):
    request_id: str = Field(min_length=8, max_length=128)


class RepaymentRequest(BaseModel):
    borrower_id: str
    request_id: str = Field(min_length=8, max_length=128)


def handle(action):
    try:
        return action()
    except DomainError as error:
        raise HTTPException(status_code=error.status, detail=str(error)) from error


@app.get("/")
def homepage():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.get("/api/dashboard")
def dashboard():
    return store.dashboard()


@app.get("/api/audit")
def audit():
    return store.ledger_audit()


@app.post("/api/transfers")
def transfer(body: TransferRequest):
    return handle(lambda: store.transfer(body.sender_id, body.recipient_id, body.amount_bdt, body.request_id))


@app.post("/api/payments")
def payment(body: TransferRequest):
    return handle(lambda: store.transfer(body.sender_id, body.recipient_id, body.amount_bdt, body.request_id, payment=True))


@app.post("/api/credit/quote")
def quote(body: CreditQuoteRequest):
    return handle(lambda: store.credit_quote(body.borrower_id, body.biller_id, body.category, body.amount_bdt, body.term_days))


@app.post("/api/credit/simulate")
def simulate_credit(body: CreditRequest):
    return handle(lambda: store.credit_simulate(body.borrower_id, body.biller_id, body.category, body.amount_bdt, body.term_days, body.request_id))


@app.post("/api/credit/{loan_id}/repay")
def repay(loan_id: str, body: RepaymentRequest):
    return handle(lambda: store.repay(loan_id, body.borrower_id, body.request_id))


@app.post("/api/demo/reset")
def reset_demo():
    return store.reset()
