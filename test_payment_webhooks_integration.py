import os
import unittest
from unittest.mock import patch

# Ensure deterministic test environment before importing the app module
os.environ["TESTING"] = "1"
os.environ["SESSION_SECRET"] = os.environ.get("SESSION_SECRET", "test-session-secret")
os.environ["DATABASE_URL"] = "sqlite:///instance/test_ci.db"

from app import app  # noqa: E402
from payments import processor  # noqa: E402


class PaymentWebhookIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.client = app.test_client()

    def test_payme_webhook_invalid_json_returns_400(self):
        with patch.object(processor.payme, "verify_webhook", return_value=True):
            resp = self.client.post(
                "/payment/webhook/payme",
                data="{",
                content_type="application/json",
                headers={"X-PaycomSignature": "a" * 40},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json(), {"error": "Invalid JSON payload"})

    def test_payme_webhook_invalid_payload_returns_400(self):
        with patch.object(processor.payme, "verify_webhook", return_value=True):
            resp = self.client.post(
                "/payment/webhook/payme",
                json={"method": "UnknownMethod", "params": {}},
                headers={"X-PaycomSignature": "a" * 40},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json(), {"error": "Invalid payload format"})

    def test_click_webhook_invalid_payload_format(self):
        resp = self.client.post("/payment/webhook/click", data={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"error": -1, "error_note": "Invalid payload format"})

    def test_click_webhook_invalid_signature_path(self):
        resp = self.client.post(
            "/payment/webhook/click",
            data={
                "service_id": "100",
                "merchant_id": "200",
                "amount": "1000",
                "merchant_trans_id": "11",
                "action": "1",
                "sign": "a" * 32,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"error": -1, "error_note": "Invalid signature"})

    def test_uzum_webhook_invalid_payload_format_returns_400(self):
        with patch.object(processor.uzum, "verify_callback", return_value=True):
            resp = self.client.post(
                "/payment/webhook/uzum",
                json={"order_id": "5", "status": "unknown"},
                headers={"X-Uzum-Signature": "sha256=" + ("a" * 64)},
            )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json(), {"status": "error", "message": "Invalid payload format"})

    def test_uzum_webhook_pending_status_ack(self):
        with patch.object(processor.uzum, "verify_callback", return_value=True):
            resp = self.client.post(
                "/payment/webhook/uzum",
                json={"order_id": "5", "status": "pending"},
                headers={"X-Uzum-Signature": "sha256=" + ("a" * 64)},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})

    def test_uzum_webhook_success_calls_confirm_payment(self):
        payload = {"order_id": "6", "status": "success"}
        with patch.object(processor.uzum, "verify_callback", return_value=True):
            with patch.object(processor, "confirm_payment", return_value={"success": True}) as mocked_confirm:
                resp = self.client.post(
                    "/payment/webhook/uzum",
                    json=payload,
                    headers={"X-Uzum-Signature": "sha256=" + ("a" * 64)},
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json(), {"status": "ok"})
        mocked_confirm.assert_called_once_with(6, payload)


if __name__ == "__main__":
    unittest.main()

