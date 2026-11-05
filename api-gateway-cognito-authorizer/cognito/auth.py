"""Create a sandbox user or sign in through Cognito using the installed AWS CLI."""

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


def required_environment(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Set {name} using the Terraform output before running this helper.")
    return value


def aws_request(operation, payload):
    command = [
        "aws", "cognito-idp", operation,
        "--region", required_environment("AWS_REGION"),
        "--no-cli-pager", "--output", "json",
    ]
    if operation == "initiate-auth":
        # User sign-in is a public Cognito API, not an IAM-authorized admin call.
        command.append("--no-sign-request")
    try:
        # CLI stdin-file behavior varies. Use a private directory and 0600 file
        # outside the repository; the context manager removes both on exit.
        with tempfile.TemporaryDirectory(prefix="cognito-auth-") as directory:
            input_file = Path(directory) / "request.json"
            descriptor = os.open(input_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(payload, stream)
            result = subprocess.run(
                command + ["--cli-input-json", "file://" + str(input_file)],
                text=True, capture_output=True,
            )
    except FileNotFoundError:
        raise RuntimeError("Install AWS CLI v2 before running this helper.") from None
    if result.returncode:
        # AWS validation errors can repeat input values. Do not print raw errors.
        match = re.search(r"An error occurred \((\w+)\)", result.stderr)
        code = match.group(1) if match else "CLIError"
        raise RuntimeError(
            f"Cognito {operation} failed ({code}). Check your login, permissions, configuration, and credentials."
        )
    return json.loads(result.stdout or "{}")


def validate_password(password):
    if (
        len(password) < 12
        or not any(c.islower() for c in password)
        or not any(c.isupper() for c in password)
        or not any(c.isdigit() for c in password)
        or not any(not c.isalnum() for c in password)
        or not all(33 <= ord(c) <= 126 for c in password)
    ):
        raise RuntimeError("Use at least 12 printable ASCII characters with uppercase, lowercase, a number, and a symbol; no spaces.")


def create_user(username, password):
    validate_password(password)
    pool_id = required_environment("USER_POOL_ID")
    aws_request("admin-create-user", {
        "UserPoolId": pool_id,
        "Username": username,
        "MessageAction": "SUPPRESS",
    })
    aws_request("admin-set-user-password", {
        "UserPoolId": pool_id,
        "Username": username,
        "Password": password,
        "Permanent": True,
    })


def login(username, password):
    result = aws_request("initiate-auth", {
        "ClientId": required_environment("CLIENT_ID"),
        "AuthFlow": "USER_PASSWORD_AUTH",
        "AuthParameters": {"USERNAME": username, "PASSWORD": password},
    })
    token = result.get("AuthenticationResult", {}).get("IdToken")
    if not token:
        raise RuntimeError("Sign-in did not return an ID token. Complete any user challenge in Cognito before retrying.")
    return token


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create-user", "login"])
    args = parser.parse_args()
    username = os.environ.get("TEST_USERNAME", "api-test-user")
    password = getpass.getpass("Cognito user password: ")
    if args.command == "create-user":
        if password != getpass.getpass("Confirm password: "):
            raise RuntimeError("Passwords do not match.")
        create_user(username, password)
        print("Created the test user and set a permanent password.")
    else:
        # Capture stdout into ID_TOKEN; password prompts go to the terminal.
        print(login(username, password))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, KeyboardInterrupt, EOFError) as error:
        print(str(error) or "Cancelled.", file=sys.stderr)
        sys.exit(1)
