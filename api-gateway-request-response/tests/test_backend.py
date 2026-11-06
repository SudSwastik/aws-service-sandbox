import importlib.util
import json
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location(
    "backend", Path(__file__).resolve().parents[1] / "lambda/backend/lambda_function.py"
)
BACKEND = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BACKEND)


class BackendTests(unittest.TestCase):
    def test_proxy_preserves_query_arrays_but_filters_credentials(self):
        result = BACKEND.lambda_handler({
            "httpMethod": "POST", "resource": "/inspect", "body": '{"name":"a"}',
            "headers": {"X-Api-Key": "private", "Authorization": "private", "Cookie": "private", "X-Client-Name": "terminal"},
            "multiValueQueryStringParameters": {"tag": ["a", "b"]},
        }, None)
        body = json.loads(result["body"])
        self.assertEqual(body["headers"], {"x-client-name": "terminal"})
        self.assertEqual(body["multiValueQuery"]["tag"], ["a", "b"])
        self.assertEqual(body["body"], {"name": "a"})

    def test_mapped_post_and_business_rejection(self):
        event = {"integration": "mapped", "method": "POST", "query": {}}
        self.assertEqual(BACKEND.lambda_handler(event, None)["httpStatus"], 201)
        event["query"]["reject"] = "true"
        self.assertEqual(BACKEND.lambda_handler(event, None)["httpStatus"], 422)

    def test_status_route_cannot_return_arbitrary_status(self):
        for code, expected in [("404", 404), ("500", 500), ("999", 400), ("abc", 400)]:
            with self.subTest(code=code):
                self.assertEqual(BACKEND.lambda_handler({"pathParameters": {"code": code}}, None)["statusCode"], expected)


if __name__ == "__main__":
    unittest.main()
