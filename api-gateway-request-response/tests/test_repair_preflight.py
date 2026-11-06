import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

SPEC = importlib.util.spec_from_file_location(
    "repair", Path(__file__).resolve().parents[1] / "scripts/repair_preflight.py"
)
REPAIR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPAIR)


class RepairTests(unittest.TestCase):
    def test_repairs_only_options_without_redeploying_or_reading_keys(self):
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            if command[2] == "get-resources":
                value = {"items": [
                    {"id": "orders", "path": "/orders", "resourceMethods": {"POST": {}, "OPTIONS": {}}},
                    {"id": "other", "path": "/other", "resourceMethods": {"GET": {}}},
                ]}
            else:
                value = {"apiKeyRequired": False}
            return SimpleNamespace(stdout=json.dumps(value))

        REPAIR.repair("https://example.execute-api.us-east-1.amazonaws.com/dev", run=run)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][2], "update-method")
        self.assertEqual(calls[1][calls[1].index("--http-method") + 1], "OPTIONS")
        self.assertIn("op=replace,path=/apiKeyRequired,value=false", calls[1])

    def test_rejects_unrecognized_url_before_aws_calls(self):
        def run(*args, **kwargs):
            self.fail("Must not contact AWS")

        with self.assertRaises(ValueError):
            REPAIR.repair("https://example.com/dev", run=run)
