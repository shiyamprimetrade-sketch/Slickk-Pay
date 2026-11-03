"""New merchant-product safety checks. Provider HTTP is mocked."""
import unittest
from urllib.parse import parse_qs, urlparse
from app.live import Config
from tests.test_live import LiveCheckoutTests, sample


class RestrictedProductTests(unittest.TestCase):
    setUp = LiveCheckoutTests.setUp
    checkout = LiveCheckoutTests.checkout

    def test_rejects_regulated_product_categories(self):
        for name in ("Slickk Pay Wallet Topup", "Microloan disbursement", "Remittance transfer", "Stored value"):
            with self.subTest(product=name):
                body = sample()
                body["product_name"] = name
                self.assertEqual(self.checkout(body).status_code, 422)
        self.assertEqual(len(self.gateway_calls), 0)

    def test_provider_callback_urls_share_one_host(self):
        self.checkout()
        data = parse_qs(self.gateway_calls[0].content.decode())
        urls = [data[key][0] for key in ("success_url", "fail_url", "cancel_url", "ipn_url")]
        self.assertEqual(len({urlparse(url).hostname for url in urls}), 1)
        self.assertTrue(all(u.startswith(self.cfg.public_base_url + "/v1/gateway/") for u in urls))

    def test_provider_credential_field_lengths(self):
        with self.assertRaises(ValueError):
            Config(enabled=True, api_key=self.cfg.api_key, gateway_store_id="x"*31,
                   gateway_store_password="pwd").validate()
        with self.assertRaises(ValueError):
            Config(enabled=True, api_key=self.cfg.api_key, gateway_store_id="id",
                   gateway_store_password="x"*31).validate()
