"""Merchant-side catalog, deterministic invoices and price-authorisation checks.

Catalog prices are trusted only after they are provisioned by the merchant's
private server. Browser-provided price and product data are never authoritative.
All operations in this module are offline and DO NOT initiate a payment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence
import hashlib
import hmac
import json
import threading

from .primitives import (
    ConflictError, EvidenceError, InvariantError, Money, PolicyError,
    bdt_from_minor, canonical_json, evidence_hash, nonnegative_minor,
    positive_minor, reference, safe_key, timestamp, utc_iso,
)


class ProductKind(str, Enum):
    GOODS = "goods"
    MERCHANT_SERVICE = "merchant_service"
    DIGITAL_DOWNLOAD = "digital_download"
    EVENT_TICKET = "event_ticket"
    WALLET_TOPUP = "wallet_topup"
    LOAN = "loan"
    REMITTANCE = "remittance"
    EXCHANGE = "exchange"
    STORED_VALUE = "stored_value"


ALLOWED_KINDS = frozenset({ProductKind.GOODS, ProductKind.MERCHANT_SERVICE,
                           ProductKind.DIGITAL_DOWNLOAD, ProductKind.EVENT_TICKET})


@dataclass(frozen=True, slots=True)
class Product:
    merchant_id: str
    sku: str
    name: str
    kind: ProductKind
    unit_price_poisha: int
    active: bool = True
    minimum_qty: int = 1
    maximum_qty: int = 100
    tax_basis_points: int = 0
    inventory: int | None = None

    def __post_init__(self) -> None:
        reference(self.merchant_id, field_name="merchant_id", max_length=64)
        reference(self.sku, field_name="sku", max_length=64)
        if not isinstance(self.name, str) or not 2 <= len(self.name) <= 120:
            raise EvidenceError("Invalid product name")
        if any(ord(c) < 32 for c in self.name):
            raise EvidenceError("Invalid product name")
        if not isinstance(self.kind, ProductKind):
            raise EvidenceError("Unknown product kind")
        positive_minor(self.unit_price_poisha)
        if not isinstance(self.minimum_qty, int) or isinstance(self.minimum_qty, bool):
            raise EvidenceError("Quantity must be an integer")
        if not isinstance(self.maximum_qty, int) or isinstance(self.maximum_qty, bool):
            raise EvidenceError("Quantity must be an integer")
        if not 1 <= self.minimum_qty <= self.maximum_qty <= 1000:
            raise EvidenceError("Invalid quantity bounds")
        if not isinstance(self.tax_basis_points, int) or isinstance(self.tax_basis_points, bool):
            raise EvidenceError("Tax rate must be an integer basis-point value")
        if not 0 <= self.tax_basis_points <= 10_000:
            raise EvidenceError("Invalid tax rate")
        if self.inventory is not None and (isinstance(self.inventory, bool)
                                           or not isinstance(self.inventory, int)
                                           or self.inventory < 0):
            raise EvidenceError("Inventory must be nonnegative")

    @property
    def key(self) -> tuple[str, str]:
        return self.merchant_id, self.sku

    def orderable(self, quantity: int) -> bool:
        return (self.active and self.kind in ALLOWED_KINDS
                and self.minimum_qty <= quantity <= self.maximum_qty
                and (self.inventory is None or quantity <= self.inventory))


@dataclass(frozen=True, slots=True)
class LineRequest:
    sku: str
    quantity: int

    def __post_init__(self) -> None:
        reference(self.sku, field_name="sku", max_length=64)
        if isinstance(self.quantity, bool) or not isinstance(self.quantity, int):
            raise EvidenceError("Quantity must be an integer")
        if not 1 <= self.quantity <= 1000:
            raise EvidenceError("Quantity is outside allowed range")


@dataclass(frozen=True, slots=True)
class InvoiceLine:
    sku: str
    description: str
    kind: ProductKind
    quantity: int
    unit_price_poisha: int
    subtotal_poisha: int
    tax_poisha: int

    @property
    def total_poisha(self) -> int:
        return self.subtotal_poisha + self.tax_poisha

    def as_dict(self) -> dict:
        return {"sku": self.sku, "kind": self.kind.value, "quantity": self.quantity,
                "unit_price_bdt": bdt_from_minor(self.unit_price_poisha),
                "subtotal_bdt": bdt_from_minor(self.subtotal_poisha),
                "tax_bdt": bdt_from_minor(self.tax_poisha),
                "line_total_bdt": bdt_from_minor(self.total_poisha)}


@dataclass(frozen=True, slots=True)
class Invoice:
    invoice_ref: str
    merchant_id: str
    created_at: datetime
    expires_at: datetime
    lines: tuple[InvoiceLine, ...]
    subtotal_poisha: int
    tax_poisha: int
    shipping_poisha: int
    discount_poisha: int
    total_poisha: int
    catalog_version: int
    fingerprint: str

    def __post_init__(self) -> None:
        reference(self.invoice_ref, field_name="invoice_ref")
        reference(self.merchant_id, field_name="merchant_id", max_length=64)
        if timestamp(self.expires_at) <= timestamp(self.created_at):
            raise EvidenceError("Invoice must expire after creation")
        if not self.lines:
            raise EvidenceError("Invoice requires line items")
        if self.total_poisha <= 0:
            raise EvidenceError("Zero or negative invoice is prohibited")
        if self.total_poisha != (self.subtotal_poisha + self.tax_poisha
                                + self.shipping_poisha - self.discount_poisha):
            raise InvariantError("Invoice total is not balanced")
        if sum(x.subtotal_poisha for x in self.lines) != self.subtotal_poisha:
            raise InvariantError("Invoice line subtotal mismatch")
        if sum(x.tax_poisha for x in self.lines) != self.tax_poisha:
            raise InvariantError("Invoice tax subtotal mismatch")

    def as_dict(self) -> dict:
        return {"invoice_ref": self.invoice_ref, "merchant_id": self.merchant_id,
                "created_at": utc_iso(self.created_at), "expires_at": utc_iso(self.expires_at),
                "currency": "BDT", "subtotal_bdt": bdt_from_minor(self.subtotal_poisha),
                "tax_bdt": bdt_from_minor(self.tax_poisha),
                "shipping_bdt": bdt_from_minor(self.shipping_poisha),
                "discount_bdt": bdt_from_minor(self.discount_poisha),
                "total_bdt": bdt_from_minor(self.total_poisha),
                "catalog_version": self.catalog_version, "fingerprint": self.fingerprint,
                "lines": [line.as_dict() for line in self.lines]}


class MerchantCatalog:
    """In-memory reference catalog for invoice authorisation; no gateway side effects."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._products: dict[tuple[str, str], Product] = {}
        self._versions: dict[str, int] = {}
        self._invoices: dict[tuple[str, str], Invoice] = {}
        self._invoice_requests: dict[tuple[str, str], str] = {}

    def register(self, product: Product, *, replace: bool = False) -> int:
        if not isinstance(product, Product):
            raise EvidenceError("Expected Product")
        with self._lock:
            if product.key in self._products and not replace:
                raise ConflictError("Product already registered")
            self._products[product.key] = product
            version = self._versions.get(product.merchant_id, 0) + 1
            self._versions[product.merchant_id] = version
            return version

    def retire(self, merchant_id: str, sku: str) -> int:
        product = self.get(merchant_id, sku)
        return self.register(Product(product.merchant_id, product.sku, product.name,
                                     product.kind, product.unit_price_poisha,
                                     False, product.minimum_qty, product.maximum_qty,
                                     product.tax_basis_points, product.inventory), replace=True)

    def get(self, merchant_id: str, sku: str) -> Product:
        reference(merchant_id, field_name="merchant_id")
        reference(sku, field_name="sku")
        with self._lock:
            try:
                return self._products[(merchant_id, sku)]
            except KeyError as exc:
                raise EvidenceError("Unknown merchant product") from exc

    def list_active(self, merchant_id: str) -> tuple[Product, ...]:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            return tuple(sorted((p for p in self._products.values()
                                 if p.merchant_id == merchant_id and p.active
                                 and p.kind in ALLOWED_KINDS), key=lambda p: p.sku))

    @staticmethod
    def _rounded_tax(subtotal_poisha: int, basis_points: int) -> int:
        return int((Decimal(subtotal_poisha) * Decimal(basis_points) / 10_000)
                   .quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def quote(self, *, merchant_id: str, invoice_ref: str, lines: Sequence[LineRequest],
              now: datetime, valid_for_seconds: int = 900,
              shipping_poisha: int = 0, discount_poisha: int = 0) -> Invoice:
        reference(merchant_id, field_name="merchant_id")
        reference(invoice_ref, field_name="invoice_ref")
        now = timestamp(now)
        nonnegative_minor(shipping_poisha)
        nonnegative_minor(discount_poisha)
        if isinstance(valid_for_seconds, bool) or not isinstance(valid_for_seconds, int):
            raise EvidenceError("Invalid invoice validity")
        if not 30 <= valid_for_seconds <= 86_400:
            raise EvidenceError("Invoice validity outside allowed window")
        if not isinstance(lines, Sequence) or not 1 <= len(lines) <= 50:
            raise EvidenceError("Invalid invoice line count")
        if any(not isinstance(line, LineRequest) for line in lines):
            raise EvidenceError("Expected LineRequest entries")
        if len({line.sku for line in lines}) != len(lines):
            raise ConflictError("Duplicate SKU in invoice")
        with self._lock:
            request_fingerprint = evidence_hash({
                "merchant": merchant_id, "ref": invoice_ref,
                "lines": [{"sku": x.sku, "qty": x.quantity} for x in lines],
                "shipping": shipping_poisha, "discount": discount_poisha,
                "validity_seconds": valid_for_seconds,
            })
            key = (merchant_id, invoice_ref)
            previous = self._invoices.get(key)
            if previous:
                if self._invoice_requests[key] != request_fingerprint:
                    raise ConflictError("Invoice reference reused for different request")
                return previous
            products = [self.get(merchant_id, line.sku) for line in lines]
            totals: list[InvoiceLine] = []
            for item, product in zip(lines, products):
                if not product.orderable(item.quantity):
                    raise PolicyError("Product cannot be offered through merchant checkout")
                subtotal = product.unit_price_poisha * item.quantity
                tax = self._rounded_tax(subtotal, product.tax_basis_points)
                totals.append(InvoiceLine(product.sku, product.name, product.kind,
                                          item.quantity, product.unit_price_poisha,
                                          subtotal, tax))
            subtotal = sum(x.subtotal_poisha for x in totals)
            tax = sum(x.tax_poisha for x in totals)
            if discount_poisha > subtotal + tax:
                raise EvidenceError("Discount exceeds taxable invoice total")
            final = subtotal + tax + shipping_poisha - discount_poisha
            if not 1_000 <= final <= 50_000_000:
                raise PolicyError("Invoice outside configured merchant gateway range")
            catalog_version = self._versions.get(merchant_id, 0)
            digest = evidence_hash({
                "request": request_fingerprint, "catalog_version": catalog_version,
                "lines": [x.as_dict() for x in totals], "total_poisha": final,
            })
            invoice = Invoice(invoice_ref, merchant_id, now,
                              now + timedelta(seconds=valid_for_seconds),
                              tuple(totals), subtotal, tax, shipping_poisha,
                              discount_poisha, final, catalog_version, digest)
            self._invoices[key] = invoice
            self._invoice_requests[key] = request_fingerprint
            return invoice

    def authorize_checkout(self, *, merchant_id: str, invoice_ref: str, now: datetime,
                           submitted_amount_poisha: int, submitted_fingerprint: str) -> Invoice:
        reference(merchant_id, field_name="merchant_id")
        reference(invoice_ref, field_name="invoice_ref")
        positive_minor(submitted_amount_poisha)
        if not isinstance(submitted_fingerprint, str) or len(submitted_fingerprint) != 64:
            raise EvidenceError("Invalid invoice fingerprint")
        with self._lock:
            key = (merchant_id, invoice_ref)
            if key not in self._invoices:
                raise EvidenceError("Unknown invoice")
            invoice = self._invoices[key]
            if timestamp(now) >= timestamp(invoice.expires_at):
                raise PolicyError("Invoice expired")
            if not hmac.compare_digest(invoice.fingerprint, submitted_fingerprint):
                raise PolicyError("Invoice hash mismatch")
            if invoice.total_poisha != submitted_amount_poisha:
                raise PolicyError("Checkout amount differs from merchant invoice")
            if invoice.catalog_version != self._versions.get(merchant_id, 0):
                raise PolicyError("Merchant catalog has changed since invoice")
            return invoice

    def verify_no_cross_merchant_access(self, merchant_id: str, invoice_ref: str) -> bool:
        reference(merchant_id, field_name="merchant_id")
        reference(invoice_ref, field_name="invoice_ref")
        with self._lock:
            return (merchant_id, invoice_ref) in self._invoices

    def invoice_count(self, merchant_id: str) -> int:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            return sum(1 for mid, _ in self._invoices if mid == merchant_id)

    def manifest(self, merchant_id: str) -> dict[str, object]:
        reference(merchant_id, field_name="merchant_id")
        with self._lock:
            products = self.list_active(merchant_id)
            return {"merchant_id": merchant_id,
                    "catalog_version": self._versions.get(merchant_id, 0),
                    "active_product_count": len(products),
                    "orderable_skus": [p.sku for p in products],
                    "invoice_count": self.invoice_count(merchant_id)}
