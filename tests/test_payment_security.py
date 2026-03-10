import unittest

from payment_security import (
    build_click_signature_payload,
    extract_click_order_id,
    extract_payme_order_id,
    extract_positive_int,
    extract_uzum_order_id,
    normalize_md5_signature,
    normalize_sha1_signature,
    normalize_sha256_signature,
    validate_click_payload,
    validate_payme_payload,
    validate_uzum_payload,
)


class PaymentSecurityTests(unittest.TestCase):
    def test_normalize_sha1_signature_accepts_prefixed_value(self):
        raw = "sha1=" + ("a" * 40)
        self.assertEqual(normalize_sha1_signature(raw), "a" * 40)

    def test_normalize_sha1_signature_rejects_invalid_value(self):
        self.assertIsNone(normalize_sha1_signature("sha1=zzz"))

    def test_normalize_md5_signature_accepts_hex(self):
        self.assertEqual(normalize_md5_signature("ABCDEF0123456789ABCDEF0123456789"), "abcdef0123456789abcdef0123456789")

    def test_normalize_sha256_signature_accepts_v1_prefix(self):
        raw = "v1=" + ("b" * 64)
        self.assertEqual(normalize_sha256_signature(raw), "b" * 64)

    def test_extract_positive_int(self):
        self.assertEqual(extract_positive_int("123"), 123)
        self.assertIsNone(extract_positive_int("-2"))
        self.assertIsNone(extract_positive_int("abc"))

    def test_validate_payme_payload_for_perform_requires_order_id(self):
        payload_ok = {
            "method": "PerformTransaction",
            "params": {"account": {"order_id": "17"}},
        }
        payload_bad = {
            "method": "PerformTransaction",
            "params": {"account": {"order_id": "x"}},
        }
        self.assertTrue(validate_payme_payload(payload_ok))
        self.assertFalse(validate_payme_payload(payload_bad))
        self.assertEqual(extract_payme_order_id(payload_ok), 17)

    def test_validate_click_payload_checks_service_and_merchant(self):
        params = {
            "service_id": "100",
            "merchant_id": "200",
            "amount": "1000",
            "merchant_trans_id": "55",
            "action": "1",
            "sign": "f" * 32,
        }
        self.assertTrue(validate_click_payload(params, "100", "200"))
        self.assertFalse(validate_click_payload(params, "101", "200"))
        self.assertEqual(extract_click_order_id(params), 55)

    def test_build_click_signature_payload_uses_merchant_trans_id(self):
        params = {
            "service_id": "100",
            "merchant_id": "200",
            "amount": "1000.00",
            "merchant_trans_id": "90",
        }
        signature_payload = build_click_signature_payload(params)
        self.assertEqual(signature_payload["transaction_param"], "90")

    def test_validate_uzum_payload_requires_known_status(self):
        payload_ok = {"order_id": "21", "status": "success"}
        payload_bad = {"order_id": "21", "status": "unknown"}
        self.assertTrue(validate_uzum_payload(payload_ok))
        self.assertFalse(validate_uzum_payload(payload_bad))
        self.assertEqual(extract_uzum_order_id(payload_ok), 21)


if __name__ == "__main__":
    unittest.main()

