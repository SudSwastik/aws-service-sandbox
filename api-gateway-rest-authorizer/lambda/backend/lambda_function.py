"""Stateless mock API for API Gateway REST and HTTP Lambda proxy events."""

import base64
import binascii
import json


def response(status_code, payload, headers=None):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **(headers or {})},
        "body": json.dumps(payload),
        "isBase64Encoded": False,
    }


def lambda_handler(event, context):
    method = (
        event.get("httpMethod")
        or event.get("requestContext", {}).get("http", {}).get("method", "")
    ).upper()
    path = event.get("rawPath") or event.get("path") or "/"
    allowed = "GET, POST, PUT, DELETE"
    if method not in {"GET", "POST", "PUT", "DELETE"}:
        return response(405, {"message": "Method not allowed"}, {"Allow": allowed})

    body = None
    raw_body = event.get("body")
    if raw_body is not None and raw_body != "":
        try:
            if event.get("isBase64Encoded"):
                raw_body = base64.b64decode(raw_body, validate=True).decode("utf-8")
            body = json.loads(raw_body)
        except (ValueError, UnicodeError, binascii.Error, TypeError):
            return response(400, {"message": "Body must contain valid UTF-8 JSON"})

    if method in {"POST", "PUT"} and not isinstance(body, dict):
        return response(400, {"message": "POST and PUT require a JSON object body"})

    # Echo request details so callers can verify API Gateway forwarding.
    request = {
        "method": method,
        "path": path,
        "query": event.get("queryStringParameters") or {},
        "pathParameters": event.get("pathParameters") or {},
        "body": body,
    }
    if method == "GET":
        status, message, data = 200, "Mock items retrieved", [
            {"id": "1", "name": "Mock item", "status": "active"}
        ]
    elif method == "POST":
        status, message, data = 201, "Mock item created", {"id": "mock-id", **body}
    elif method == "PUT":
        status, message, data = 200, "Mock item updated", body
    else:
        status, message, data = 200, "Mock item deleted", {"deleted": True}

    return response(status, {
        "mock": True,
        "message": message,
        "data": data,
        "request": request,
    })
