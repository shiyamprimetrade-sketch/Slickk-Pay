"""Merchant invoice price-source and idempotency security tests."""
import unittest
from datetime import datetime, timedelta, timezone
from dataclasses import replace

from app.ops.catalog import MerchantCatalog, Product, ProductKind, LineRequest
from app.ops.primitives import ConflictError, EvidenceError, PolicyError

NOW=datetime(2026,11,3,12,0,tzinfo=timezone.utc)


def item(sku="s1", *, merchant="merchant-A", price=12000, kind=ProductKind.GOODS,
         active=True, tax=1500, inventory=100):
    return Product(merchant,sku,"Blue cotton shirt",kind,price,active,
                   minimum_qty=1,maximum_qty=20,tax_basis_points=tax,
                   inventory=inventory)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog=MerchantCatalog()
        self.catalog.register(item())
        self.catalog.register(item("s2",price=5000,kind=ProductKind.MERCHANT_SERVICE,tax=0))

    def quote(self, *, merchant="merchant-A", ref="inv-A", qty=2,
              discount=0, shipping=0, sku="s1", now=NOW):
        return self.catalog.quote(merchant_id=merchant, invoice_ref=ref,
                                  lines=[LineRequest(sku,qty)], now=now,
                                  discount_poisha=discount,shipping_poisha=shipping)

    def test_catalog_lists_active_products(self):
        products=self.catalog.list_active("merchant-A")
        self.assertEqual([p.sku for p in products],["s1","s2"])
        self.assertEqual(self.catalog.manifest("merchant-A")["catalog_version"],2)

    def test_invoice_exact_amount_and_tax(self):
        invoice=self.quote()
        self.assertEqual(invoice.subtotal_poisha,24000)
        self.assertEqual(invoice.tax_poisha,3600)
        self.assertEqual(invoice.total_poisha,27600)
        self.assertEqual(invoice.as_dict()["total_bdt"],"276.00")

    def test_invoice_shipping_and_discount(self):
        invoice=self.quote(discount=500,shipping=2000)
        self.assertEqual(invoice.total_poisha,29100)
        self.assertEqual(invoice.as_dict()["discount_bdt"],"5.00")
        self.assertEqual(invoice.as_dict()["shipping_bdt"],"20.00")

    def test_invoice_idempotent_ref(self):
        first=self.quote()
        second=self.quote(now=NOW+timedelta(minutes=2))
        self.assertIs(first,second)
        self.assertEqual(self.catalog.invoice_count("merchant-A"),1)

    def test_invoice_ref_collision(self):
        self.quote()
        with self.assertRaises(ConflictError):
            self.quote(qty=3)

    def test_checkout_fingerprint_and_price_match(self):
        invoice=self.quote()
        authorized=self.catalog.authorize_checkout(merchant_id="merchant-A",invoice_ref="inv-A",
            now=NOW+timedelta(seconds=1),submitted_amount_poisha=invoice.total_poisha,
            submitted_fingerprint=invoice.fingerprint)
        self.assertIs(invoice,authorized)

    def test_price_tamper_is_rejected(self):
        invoice=self.quote()
        with self.assertRaises(PolicyError):
            self.catalog.authorize_checkout(merchant_id="merchant-A",invoice_ref="inv-A",now=NOW,
                submitted_amount_poisha=invoice.total_poisha+1,submitted_fingerprint=invoice.fingerprint)

    def test_fingerprint_tamper_is_rejected(self):
        invoice=self.quote()
        with self.assertRaises(PolicyError):
            self.catalog.authorize_checkout(merchant_id="merchant-A",invoice_ref="inv-A",now=NOW,
                submitted_amount_poisha=invoice.total_poisha,submitted_fingerprint="1"*64)

    def test_expiry_boundary_is_exclusive(self):
        invoice=self.quote()
        with self.assertRaises(PolicyError):
            self.catalog.authorize_checkout(merchant_id="merchant-A",invoice_ref="inv-A",
                now=invoice.expires_at,submitted_amount_poisha=invoice.total_poisha,
                submitted_fingerprint=invoice.fingerprint)

    def test_catalog_change_invalidates_prior_quote(self):
        invoice=self.quote()
        self.catalog.register(item(price=13000),replace=True)
        with self.assertRaises(PolicyError):
            self.catalog.authorize_checkout(merchant_id="merchant-A",invoice_ref="inv-A",now=NOW,
                submitted_amount_poisha=invoice.total_poisha,submitted_fingerprint=invoice.fingerprint)

    def test_cross_merchant_authorization_is_rejected(self):
        self.quote()
        with self.assertRaises(EvidenceError):
            self.catalog.authorize_checkout(merchant_id="merchant-B",invoice_ref="inv-A",now=NOW,
                submitted_amount_poisha=27600,submitted_fingerprint="a"*64)

    def test_retired_product_cannot_be_quoted(self):
        self.catalog.retire("merchant-A","s1")
        with self.assertRaises(PolicyError):
            self.quote()

    def test_restricted_wallet_product_blocked(self):
        for kind in (ProductKind.WALLET_TOPUP,ProductKind.LOAN,ProductKind.REMITTANCE,
                     ProductKind.EXCHANGE,ProductKind.STORED_VALUE):
            with self.subTest(kind=kind.value):
                sku="r-"+kind.value
                self.catalog.register(item(sku,kind=kind))
                with self.assertRaises(PolicyError):
                    self.quote(sku=sku,ref="invoice-"+kind.value)

    def test_wrong_inventory_and_quantity_rejected(self):
        self.catalog.register(item("low",inventory=1),replace=False)
        with self.assertRaises(PolicyError):
            self.quote(sku="low",ref="low-1",qty=2)
        with self.assertRaises(EvidenceError):
            LineRequest("s1",0)

    def test_duplicate_sku_rejected(self):
        with self.assertRaises(ConflictError):
            self.catalog.quote(merchant_id="merchant-A",invoice_ref="two",now=NOW,
                lines=[LineRequest("s1",1),LineRequest("s1",1)])

    def test_discount_cannot_exceed_goods(self):
        with self.assertRaises(EvidenceError):
            self.quote(discount=999999)

    def test_gateway_range_enforced(self):
        self.catalog.register(item("cheap",price=1,tax=0))
        with self.assertRaises(PolicyError):
            self.quote(ref="cheap-1",sku="cheap")

    def test_tax_half_up_rounding(self):
        self.catalog.register(item("round",price=101,tax=500))
        invoice=self.quote(ref="rounding",sku="round",qty=10)
        self.assertEqual(invoice.tax_poisha,51)

    def test_registration_rejects_collision(self):
        with self.assertRaises(ConflictError):
            self.catalog.register(item())

    def test_sku_and_merchant_scopes(self):
        self.catalog.register(item("s1",merchant="merchant-B"))
        other=self.catalog.quote(merchant_id="merchant-B",invoice_ref="inv-A",
                                 lines=[LineRequest("s1",1)],now=NOW)
        own=self.quote(ref="inv-A")
        self.assertNotEqual(own.fingerprint,other.fingerprint)
        self.assertEqual(self.catalog.invoice_count("merchant-B"),1)

    def test_invalid_catalog_records(self):
        with self.assertRaises(EvidenceError):
            item(price=-1)
        with self.assertRaises(EvidenceError):
            item(tax=10001)
        with self.assertRaises(EvidenceError):
            item(inventory=-1)
        with self.assertRaises(EvidenceError):
            Product("merchant-A","bad","C",ProductKind.GOODS,100)


if __name__=="__main__":
    unittest.main()
