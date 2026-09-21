import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import RuntimeEvent


def create_access_token(sub: str, tenant_id: str, role: str, aud: str | None = None) -> tuple[str, int]:
    expires_minutes = settings.jwt_expiry_minutes
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {
        "sub": sub,
        "tenant_id": tenant_id,
        "role": role,
        "aud": aud or settings.jwt_audience,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, expires_minutes * 60


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc


def validate_role_for_source(role: str, source: str) -> bool:
    app_roles = {"zoho-simulator", "scheduler"}
    if source == "zoho":
        return role in app_roles or role == "zoho-simulator"
    if source == "scheduler":
        return role in app_roles or role == "scheduler"
    if source == "teams":
        return role in {"sales-user", "teams-sales-user"} or role.startswith("sales")
    return False


def sign_zoho_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hmac.new(
        settings.zoho_webhook_secret.encode(),
        body.encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_zoho_signature(payload: dict[str, Any], signature: str | None) -> bool:
    if not signature:
        return False
    expected = sign_zoho_payload(payload)
    return hmac.compare_digest(expected, signature)


def add_runtime_event(
    db: Session,
    *,
    stage: str,
    component: str,
    action: str,
    status: str,
    message: str = "",
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> RuntimeEvent:
    event = RuntimeEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:16].upper()}",
        run_id=run_id,
        stage=stage,
        component=component,
        action=action,
        status=status,
        message=message,
        metadata_json=json.dumps(metadata or {}),
    )
    db.add(event)
    db.flush()
    return event
