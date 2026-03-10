import unittest
from types import SimpleNamespace

from rate_limiter import InMemoryRateLimiter, get_client_ip


class RateLimiterTests(unittest.TestCase):
    def test_allows_within_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(3):
            allowed, retry_after = limiter.is_allowed("k1", limit=3, window_seconds=60)
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0)

    def test_blocks_after_limit(self):
        limiter = InMemoryRateLimiter()
        for _ in range(2):
            allowed, _ = limiter.is_allowed("k2", limit=2, window_seconds=60)
            self.assertTrue(allowed)

        allowed, retry_after = limiter.is_allowed("k2", limit=2, window_seconds=60)
        self.assertFalse(allowed)
        self.assertGreaterEqual(retry_after, 1)

    def test_get_client_ip_prefers_x_forwarded_for(self):
        req = SimpleNamespace(
            headers={"X-Forwarded-For": "10.0.0.1, 10.0.0.2"},
            remote_addr="127.0.0.1",
        )
        self.assertEqual(get_client_ip(req), "10.0.0.1")

    def test_get_client_ip_uses_x_real_ip_when_no_forwarded_for(self):
        req = SimpleNamespace(
            headers={"X-Real-IP": "192.168.1.15"},
            remote_addr="127.0.0.1",
        )
        self.assertEqual(get_client_ip(req), "192.168.1.15")


if __name__ == "__main__":
    unittest.main()
