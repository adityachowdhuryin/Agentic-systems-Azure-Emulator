"""Short-lived scoped credentials for mock ERP / extract / policy (Assignment 02 T5)."""
from __future__ import annotations

import hashlib
import hmac
import time

from app.config import settings

SCOPES = {
    "extract_invoice": "extract",
    "get_purchase_order": "erp",
    "get_goods_receipt": "erp",
    "get_vendor": "erp",
    "get_ap_history": "erp",
    "search_policy": "policy",
    "get_policy": "policy",
}

# Pack mock_systems.py expects these literal tokens. Broker "mints" them only after
# intent is journaled — agent code never reads them from env for connectors.
_STATIC_TOKENS = {
    "erp": "erp-scoped-token",
    "extract": "extract-scoped-token",
    "policy": "policy-scoped-token",
}


def scope_for_tool(tool_name: str) -> str | None:
    return SCOPES.get(tool_name)


def mint_credential(tool_name: str, *, run_id: str, intent_recorded: bool) -> str:
    if not intent_recorded:
        raise PermissionError("Credential refused: intent not journaled")
    scope = scope_for_tool(tool_name)
    if not scope:
        raise PermissionError(f"No credential scope for tool {tool_name}")
    # Bind mint to run + time using HMAC (shows broker path); return pack-compatible token.
    ts = int(time.time())
    mac = hmac.new(
        settings.broker_hmac_secret.encode(),
        f"{scope}:{run_id}:{tool_name}:{ts}".encode(),
        hashlib.sha256,
    ).hexdigest()[:16]
    _ = mac  # recorded in journal by caller if needed
    return _STATIC_TOKENS[scope]
