"""Short-lived scoped credentials for mock ERP / extract / policy (Assignment 02 T5).

Agent path: mint only after a journal intent row exists for this run+tool.
Returns HMAC tokens (b1.*); never returns long-lived static pack tokens.
Static tokens remain documented mock fallbacks for manual curls only.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from sqlalchemy.orm import Session

from app.config import settings
from app.database import JournalTurn

SCOPES = {
    "extract_invoice": "extract",
    "get_purchase_order": "erp",
    "get_goods_receipt": "erp",
    "get_vendor": "erp",
    "get_ap_history": "erp",
    "search_policy": "policy",
    "get_policy": "policy",
}

# Pack-compatible literals — mocks still accept these; agent never mints them.
STATIC_TOKENS = {
    "erp": "erp-scoped-token",
    "extract": "extract-scoped-token",
    "policy": "policy-scoped-token",
}

TOKEN_TTL_SECONDS = 120
TOKEN_PREFIX = "b1"


def scope_for_tool(tool_name: str) -> str | None:
    return SCOPES.get(tool_name)


def _secret() -> str:
    return settings.broker_hmac_secret


def _sign(scope: str, run_id: str, exp: int) -> str:
    return hmac.new(
        _secret().encode(),
        f"{scope}:{run_id}:{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def format_token(*, scope: str, run_id: str, exp: int | None = None) -> str:
    exp = exp if exp is not None else int(time.time()) + TOKEN_TTL_SECONDS
    mac = _sign(scope, run_id, exp)
    return f"{TOKEN_PREFIX}.{scope}.{run_id}.{exp}.{mac}"


def parse_token(token: str) -> tuple[str, str, int, str] | None:
    """Return (scope, run_id, exp, mac) or None if not a b1 token."""
    if not token or not token.startswith(f"{TOKEN_PREFIX}."):
        return None
    parts = token.split(".")
    if len(parts) < 5:
        return None
    # b1.scope.run_id.exp.mac — run_id may contain dots rarely; use fixed ends
    _prefix, scope, exp_s, mac = parts[0], parts[1], parts[-2], parts[-1]
    run_id = ".".join(parts[2:-2])
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if not scope or not run_id or not mac:
        return None
    return scope, run_id, exp, mac


def verify_token(token: str, *, expected_scope: str, now: int | None = None) -> bool:
    """Validate short-lived broker token for a system scope."""
    parsed = parse_token(token)
    if not parsed:
        return False
    scope, run_id, exp, mac = parsed
    if scope != expected_scope:
        return False
    ts = now if now is not None else int(time.time())
    if ts > exp:
        return False
    expected = _sign(scope, run_id, exp)
    return hmac.compare_digest(mac, expected)


def _has_open_intent(db: Session, *, run_id: str, tool_name: str) -> bool:
    rows = (
        db.query(JournalTurn)
        .filter(JournalTurn.run_id == run_id, JournalTurn.tool_name == tool_name)
        .order_by(JournalTurn.id.desc())
        .limit(5)
        .all()
    )
    for row in rows:
        try:
            result = json.loads(row.tool_result_json or "{}")
        except json.JSONDecodeError:
            continue
        if result.get("status") == "intent_recorded":
            return True
    return False


def mint_credential(db: Session, *, run_id: str, tool_name: str) -> str:
    """Mint only if journal shows intent for this run+tool. Returns b1.* HMAC token."""
    if not _has_open_intent(db, run_id=run_id, tool_name=tool_name):
        raise PermissionError("Credential refused: intent not journaled")
    scope = scope_for_tool(tool_name)
    if not scope:
        raise PermissionError(f"No credential scope for tool {tool_name}")
    return format_token(scope=scope, run_id=run_id)
