import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.correlation import new_correlation_id
from app.database import get_db
from app.error_utils import band_a_error_detail
from app.exceptions import BandAError, ValidationError
from app.ingestion.teams_inbound_adapter import TeamsInboundAdapter
from app.schemas import IngestionLogRow, IngestionLogsResponse
from app.services.ingestion_logs import list_ingestion_logs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["teams"])


def verify_teams_bridge_key(
    x_teams_bridge_key: Annotated[str | None, Header()] = None,
) -> None:
    if not x_teams_bridge_key or x_teams_bridge_key != settings.teams_bridge_key:
        raise HTTPException(status_code=401, detail="Invalid teams bridge key")


@router.post("/webhooks/teams")
async def teams_inbound_webhook(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(verify_teams_bridge_key),
):
    """
    Accept forwarded Microsoft Teams bot activities.

    Always queues Band B work (always_queue). Caller / bot polls finding.
    """
    correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
    try:
        raw: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc

    adapter = TeamsInboundAdapter(db)
    try:
        result = adapter.process_inbound_message(raw, correlation_id=correlation_id)
        db.commit()
        return {"status": "accepted", **result}
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail=band_a_error_detail(exc)) from exc
    except Exception as exc:
        db.rollback()
        logger.exception("Teams webhook failed correlation_id=%s", correlation_id)
        raise HTTPException(
            status_code=500,
            detail=f"Teams ingest failed: {type(exc).__name__}: {str(exc)[:400]}",
        ) from exc


@router.get("/ingestion-logs", response_model=IngestionLogsResponse)
def get_ingestion_logs(
    source: str = Query("teams", pattern="^(teams)$"),
    limit: int = Query(25, ge=1, le=50),
    db: Session = Depends(get_db),
    _: None = Depends(verify_teams_bridge_key),
):
    """Ingestion log rows for Teams bot Adaptive Card (real Teams inbound only)."""
    rows = list_ingestion_logs(db, source=source, limit=limit)
    return IngestionLogsResponse(
        source=source,
        count=len(rows),
        rows=[IngestionLogRow(**row) for row in rows],
    )


@router.get("/webhooks/teams/health")
def teams_webhook_health():
    return {
        "status": "ok",
        "tenant_id": settings.teams_tenant_id,
        "invoice_case_tag": "Message CASE-01 … CASE-12 for invoice review",
        "dispatch": "always_queue",
    }
