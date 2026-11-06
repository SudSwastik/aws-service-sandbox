"""Live checks. Uses API_URL/API_KEY environment variables; never prints the key."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


PREFLIGHT_HEADERS = {
    "Origin": "https://example.com",
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type,x-api-key,x-client-name",
}


def request(path, method="GET", body=None, key=True, extra=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["x-api-key"] = os.environ["API_KEY"]
    headers.update(extra or {})
    data = json.dumps(body).encode() if body is not None else None
    req = Request(os.environ["API_URL"].rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        response = urlopen(req, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        return response.code, response.headers, json.loads(response.read())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rate", action="store_true", help="Also send a bounded burst of 40 requests")
    args = parser.parse_args()
    if not os.environ.get("API_URL") or not os.environ.get("API_KEY"):
        parser.error("Set API_URL and API_KEY from Terraform outputs first")
    cases = [
        ("public health", "/health", {}, 200),
        ("missing key", "/inspect", {"key": False}, 403),
        ("invalid key", "/inspect", {"extra": {"x-api-key": "invalid"}}, 403),
        ("proxy query", "/inspect?tag=a&tag=b", {"extra": {"X-Client-Name": "terminal"}}, 200),
        ("proxy body", "/inspect", {"method": "POST", "body": {"hello": "world"}}, 200),
        ("mapped create", "/orders?currency=eur", {"method": "POST", "body": {"name": "Book", "quantity": 2}, "extra": {"x-client-name": "terminal"}}, 201),
        ("missing header", "/orders/42", {}, 400),
        ("invalid body", "/orders", {"method": "POST", "body": {"quantity": 0}, "extra": {"x-client-name": "terminal"}}, 400),
        ("mapped get", "/orders/42", {"extra": {"x-client-name": "terminal"}}, 200),
        ("mapped update", "/orders/42", {"method": "PUT", "body": {"name": "Book", "quantity": 3}, "extra": {"x-client-name": "terminal"}}, 200),
        ("mapped delete", "/orders/42", {"method": "DELETE", "extra": {"x-client-name": "terminal"}}, 200),
        ("business rejection", "/orders/42?reject=true", {"extra": {"x-client-name": "terminal"}}, 422),
        ("greedy route", "/files/reports/2026/report.json", {}, 200),
        ("custom status", "/status/404", {}, 404),
        ("preflight", "/orders", {"method": "OPTIONS", "key": False, "extra": PREFLIGHT_HEADERS}, 200),
    ]
    for name, path, kwargs, expected in cases:
        # Keep functional tests below the default 2 requests/second rate.
        time.sleep(1)
        status, headers, body = request(path, **kwargs)
        # Only print known gateway error labels, never arbitrary echoed payloads.
        error_label = body.get("error") if isinstance(body, dict) else None
        safe_error = error_label if error_label in {
            "INVALID_API_KEY", "THROTTLED", "QUOTA_EXCEEDED",
            "BAD_REQUEST_BODY", "BAD_REQUEST_PARAMETERS",
        } else "unclassified gateway response"
        assert status == expected, (
            f"{name}: expected {expected}, got {status} ({safe_error}). "
            "Check the deployed method and redeploy the updated Terraform plan."
        )
        if name == "proxy query":
            assert body["multiValueQuery"]["tag"] == ["a", "b"]
            assert "x-api-key" not in body["headers"]
        if name == "mapped create":
            assert body["gatewayTransformed"] is True
            assert body["data"]["query"]["currency"] == "EUR"
            assert body["data"]["headers"]["clientName"] == "terminal"
            assert body["data"]["body"] == {"source": "api-gateway", "payload": {"name": "Book", "quantity": 2}}
            assert "internalDebug" not in body
            assert headers["X-Response-Source"] == "api-gateway-mapping"
            assert headers["X-Backend-Version"] == "1"
        if name == "preflight":
            assert headers["Access-Control-Allow-Origin"] == "*"
            assert "POST" in headers["Access-Control-Allow-Methods"]
            assert "x-api-key" in headers["Access-Control-Allow-Headers"].lower()
        print(f"PASS {name}: HTTP {status}")
    print(f"All {len(cases)} functional checks passed.")
    if args.rate:
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(lambda _: request("/inspect")[0], range(40)))
        elapsed = time.monotonic() - started
        print("Burst status counts:", dict(Counter(statuses)))
        print(f"Sent {len(statuses)} requests with up to 10 workers in {elapsed:.2f}s.")
        unexpected = set(statuses) - {200, 429}
        assert not unexpected, f"Unexpected burst HTTP statuses: {sorted(unexpected)}"
        print("429 is expected at default limits, but AWS throttling is best effort.")
        print("This concurrent test does not verify a strict per-second request ceiling.")


if __name__ == "__main__":
    main()
