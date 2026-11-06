"""Clear deployed OPTIONS API-key flags. Redeploy with Terraform afterward."""
import json
import os
import re
import subprocess
from urllib.parse import urlparse


def repair(api_url, run=subprocess.run):
    host = urlparse(api_url).hostname or ""
    match = re.fullmatch(r"([a-z0-9]+)\.execute-api\.([a-z0-9-]+)\.amazonaws\.com", host)
    if not match:
        raise ValueError("Set API_URL to this project's Terraform api_url output")
    api_id, region = match.groups()

    def aws(operation, *args):
        result = run([
            "aws", "apigateway", operation, "--region", region,
            "--rest-api-id", api_id, *args, "--output", "json", "--no-cli-pager",
        ], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    resources = aws("get-resources")["items"]
    methods = [r for r in resources if "OPTIONS" in r.get("resourceMethods", {})]
    if not methods:
        raise RuntimeError("No OPTIONS methods found; verify API_URL and deployment")
    for resource in methods:
        response = aws(
            "update-method", "--resource-id", resource["id"], "--http-method", "OPTIONS",
            "--patch-operations", "op=replace,path=/apiKeyRequired,value=false",
        )
        if response.get("apiKeyRequired") is not False:
            raise RuntimeError("AWS did not confirm the public OPTIONS setting")
        print(f"OPTIONS {resource['path']}: apiKeyRequired=false")
    print("Now replace the Terraform API deployment to publish these method settings.")


if __name__ == "__main__":
    repair(os.environ.get("API_URL", ""))
