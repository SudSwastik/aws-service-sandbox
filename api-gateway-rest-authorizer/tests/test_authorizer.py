"""Local security behavior checks; no AWS calls or credentials needed."""

import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "lambda/authorizer/lambda_function.py"
SPEC = importlib.util.spec_from_file_location("authorizer", SOURCE)
AUTHORIZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTHORIZER)
TOKEN = "local-test-token-with-at-least-32-characters"
METHOD_ARN = "arn:aws:execute-api:us-east-1:123456789012:example/dev/GET/items"


class AuthorizerTests(unittest.TestCase):
    def invoke(self, authorization, event_type="TOKEN"):
        return AUTHORIZER.lambda_handler({
            "type": event_type,
            "authorizationToken": authorization,
            "methodArn": METHOD_ARN,
        }, None)

    @patch.dict(os.environ, {"AUTH_TOKEN": TOKEN})
    def test_valid_token_allows_only_requested_method(self):
        result = self.invoke("Bearer " + TOKEN)
        statement = result["policyDocument"]["Statement"][0]
        self.assertEqual(statement["Effect"], "Allow")
        self.assertEqual(statement["Resource"], METHOD_ARN)
        self.assertNotIn(TOKEN, str(result))

    @patch.dict(os.environ, {"AUTH_TOKEN": TOKEN})
    def test_scheme_is_case_insensitive(self):
        self.assertEqual(self.invoke("bearer " + TOKEN)["principalId"], "sandbox-client")

    @patch.dict(os.environ, {"AUTH_TOKEN": TOKEN})
    def test_invalid_or_missing_credentials_are_rejected(self):
        for value in ("", None, "Bearer", "Basic " + TOKEN, "Bearer wrong", "Bearer " + TOKEN.upper(), "Bearer " + TOKEN + " extra", "Bearer \u2603"):
            with self.subTest(value=value), self.assertRaisesRegex(Exception, "^Unauthorized$"):
                self.invoke(value)

    @patch.dict(os.environ, {"AUTH_TOKEN": ""})
    def test_missing_configuration_fails_closed(self):
        with self.assertRaisesRegex(Exception, "^Unauthorized$"):
            self.invoke("Bearer " + TOKEN)

    @patch.dict(os.environ, {"AUTH_TOKEN": TOKEN})
    def test_wrong_event_type_is_rejected(self):
        with self.assertRaisesRegex(Exception, "^Unauthorized$"):
            self.invoke("Bearer " + TOKEN, "REQUEST")


if __name__ == "__main__":
    unittest.main()
