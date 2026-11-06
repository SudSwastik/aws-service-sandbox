"""Compare REST proxy events with events constructed by gateway VTL templates."""
import base64
import json


def lambda_handler(event, context):
    if event.get("integration") == "mapped":
        # Return data, not a proxy response. API Gateway builds the HTTP response.
        rejected = event.get("query", {}).get("reject") == "true"
        return {
            "result": "rejected" if rejected else "accepted",
            "received": event,
            "httpStatus": 422 if rejected else (201 if event["method"] == "POST" else 200),
            "backendVersion": "1",
            "internalDebug": "This field must be removed by the response template.",
        }

    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body")
    if event.get("isBase64Encoded") and body is not None:
        body = base64.b64decode(body).decode("utf-8", errors="replace")
    if body:
        try:
            body = json.loads(body)
        except (ValueError, TypeError):
            pass
    code = (event.get("pathParameters") or {}).get("code", "200")
    status = int(code) if code in {"200", "201", "400", "404", "422", "500"} else 400
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "X-Response-Source": "lambda-proxy",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({
            "integration": "proxy",
            "method": event.get("httpMethod"),
            "route": event.get("resource"),
            "path": event.get("path"),
            "pathParameters": event.get("pathParameters") or {},
            "query": event.get("queryStringParameters") or {},
            "multiValueQuery": event.get("multiValueQueryStringParameters") or {},
            # An allowlist avoids returning API keys, cookies or auth headers.
            "headers": {k: v for k, v in headers.items() if k in {
                "content-type", "x-client-name", "x-trace-id"
            }},
            "body": body,
        }),
    }
