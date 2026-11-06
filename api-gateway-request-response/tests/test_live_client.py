"""Check the preflight test's wire request without making an AWS request."""
import importlib.util
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "live_client", Path(__file__).resolve().parents[1] / "scripts/test_api.py"
)
CLIENT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLIENT)


class LiveClientTests(unittest.TestCase):
    def test_preflight_sends_browser_headers_without_key(self):
        response = io.BytesIO(b'{}')
        response.code = 200
        response.headers = {}
        with patch.dict(os.environ, {"API_URL": "https://example.com/dev", "API_KEY": "private"}):
            with patch.object(CLIENT, "urlopen", return_value=response) as send:
                CLIENT.request("/orders", method="OPTIONS", key=False, extra=CLIENT.PREFLIGHT_HEADERS)
        request = send.call_args.args[0]
        self.assertEqual(request.get_method(), "OPTIONS")
        headers = {k.lower(): v for k, v in request.header_items()}
        self.assertNotIn("x-api-key", headers)
        self.assertEqual(headers["origin"], "https://example.com")
        self.assertEqual(headers["access-control-request-method"], "POST")
        self.assertIn("x-api-key", headers["access-control-request-headers"])
