"""Check helper behavior locally; JWT validation is delegated to API Gateway."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "cognito/auth.py"
SPEC = importlib.util.spec_from_file_location("cognito_auth", SOURCE)
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class AuthHelperTests(unittest.TestCase):
    @patch.dict(os.environ, {"AWS_REGION": "us-east-1"})
    @patch.object(AUTH.subprocess, "run")
    def test_login_password_uses_private_file_not_command_arguments(self, run):
        payload = {"AuthParameters": {"PASSWORD": "local-test-password"}}
        captured_paths = []

        def check_request(command, **kwargs):
            path = Path(command[command.index("--cli-input-json") + 1].removeprefix("file://"))
            captured_paths.append(path)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), payload)
            return subprocess.CompletedProcess([], 0, '{"AuthenticationResult":{"IdToken":"test-id-token"}}', "")

        run.side_effect = check_request
        AUTH.aws_request("initiate-auth", payload)
        command = run.call_args.args[0]
        self.assertNotIn("local-test-password", " ".join(command))
        self.assertIn("--no-sign-request", command)
        self.assertFalse(captured_paths[0].exists())

    @patch.dict(os.environ, {"AWS_REGION": "us-east-1"})
    @patch.object(AUTH.subprocess, "run")
    def test_admin_operation_is_signed(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, "{}", "")
        AUTH.aws_request("admin-create-user", {})
        self.assertNotIn("--no-sign-request", run.call_args.args[0])

    @patch.dict(os.environ, {"AWS_REGION": "us-east-1"})
    @patch.object(AUTH.subprocess, "run")
    def test_errors_do_not_echo_passwords(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, "", "An error occurred (InvalidPasswordException): local-secret-value")
        with self.assertRaises(RuntimeError) as error:
            AUTH.aws_request("admin-set-user-password", {})
        self.assertIn("InvalidPasswordException", str(error.exception))
        self.assertNotIn("local-secret-value", str(error.exception))
        path = Path(run.call_args.args[0][-1].removeprefix("file://"))
        self.assertFalse(path.exists())

    @patch.dict(os.environ, {"CLIENT_ID": "test-client"})
    @patch.object(AUTH, "aws_request")
    def test_login_returns_id_token_instead_of_access_token(self, request):
        request.return_value = {"AuthenticationResult": {"IdToken": "test-id-token", "AccessToken": "test-access-token"}}
        self.assertEqual(AUTH.login("test-user", "local-test-password"), "test-id-token")

    @patch.dict(os.environ, {"CLIENT_ID": "test-client"})
    @patch.object(AUTH, "aws_request", return_value={"ChallengeName": "NEW_PASSWORD_REQUIRED"})
    def test_unfinished_login_does_not_return_a_token(self, request):
        with self.assertRaises(RuntimeError):
            AUTH.login("test-user", "local-test-password")

    @patch.object(AUTH, "aws_request")
    def test_weak_password_is_rejected_before_aws_calls(self, request):
        with self.assertRaises(RuntimeError):
            AUTH.create_user("test-user", "short")
        request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
