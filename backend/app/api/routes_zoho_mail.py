from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.correlation import new_correlation_id
from app.database import get_db
from app.error_utils import band_a_error_detail
from app.exceptions import BandAError, ValidationError
from app.ingestion.zoho_mail_adapter import ZohoMailAdapter

router = APIRouter(prefix="/api/v1", tags=["zoho-mail"])


def verify_mail_bridge_key(
    x_mail_bridge_key: Annotated[str | None, Header()] = None,
) -> None:
    if not x_mail_bridge_key or x_mail_bridge_key != settings.mail_bridge_key:
        raise HTTPException(status_code=401, detail="Invalid mail bridge key")


@router.post("/webhooks/zoho-mail")
async def zoho_mail_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(verify_mail_bridge_key),
):
    """
    Accept raw Zoho Mail / Zoho Flow webhook payloads.

    - Attachment (.json/.txt) or body paste with pack-shaped invoice → invoice_review + Band B
    - Otherwise → invoice_review non_invoice path (Band B exception:not_an_invoice)
    """
    correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
    try:
        raw: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc

    adapter = ZohoMailAdapter(db)
    try:
        result = adapter.process_inbound_mail(raw, correlation_id=correlation_id)
        db.commit()
        return {"status": "accepted", **result}
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail=band_a_error_detail(exc)) from exc


@router.get("/webhooks/zoho-mail/health")
def zoho_mail_health():
    return {
        "status": "ok",
        "monitor_address": settings.mail_monitor_address,
        "tenant_id": settings.mail_tenant_id,
        "invoice_ingress": "Attach or paste pack-shaped .json/.txt invoice (supplier_id required)",
    }
