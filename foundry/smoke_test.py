"""
Foundry SDK smoke test (Azure AI Projects 2.x).

Prereqs:
  1. Azure CLI installed and: az login
  2. A Foundry project + model deployment
  3. Copy .env.example -> .env and fill FOUNDRY_PROJECT_ENDPOINT + FOUNDRY_MODEL_NAME
  4. Your Entra identity has a Foundry project role (e.g. Azure AI User)

Run:
  cd foundry && .venv/bin/python smoke_test.py
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv()

endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
model = os.getenv("FOUNDRY_MODEL_NAME", "").strip()

if not endpoint or not model:
    print(
        "Missing FOUNDRY_PROJECT_ENDPOINT or FOUNDRY_MODEL_NAME.\n"
        "Copy foundry/.env.example to foundry/.env and fill both values.",
        file=sys.stderr,
    )
    sys.exit(1)

print(f"Endpoint: {endpoint}")
print(f"Model:    {model}")
print("Authenticating with DefaultAzureCredential (uses az login)…")

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    with project_client.get_openai_client() as openai_client:
        response = openai_client.responses.create(
            model=model,
            input="Reply with exactly: foundry-sdk-ok",
        )
        text = getattr(response, "output_text", None) or str(response)
        print(f"Response: {text}")

print("Smoke test finished.")
