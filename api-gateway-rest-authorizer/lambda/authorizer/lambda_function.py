"""REST API TOKEN authorizer using a configured bearer token for sandbox tests."""

import hmac
import os


def lambda_handler(event, context):
    expected = os.environ.get("AUTH_TOKEN", "")
    authorization = event.get("authorizationToken", "")
    if not isinstance(authorization, str):
        raise Exception("Unauthorized")
    parts = authorization.split()
    if (
        event.get("type") != "TOKEN"
        or not expected
        or len(parts) != 2
        or parts[0].lower() != "bearer"
        or not hmac.compare_digest(parts[1].encode("utf-8"), expected.encode("utf-8"))
    ):
        # API Gateway maps this specific error to HTTP 401. Never log the token.
        raise Exception("Unauthorized")

    return {
        "principalId": "sandbox-client",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{
                "Action": "execute-api:Invoke",
                "Effect": "Allow",
                "Resource": event["methodArn"],
            }],
        },
        "context": {"authentication": "bearer-token"},
    }
