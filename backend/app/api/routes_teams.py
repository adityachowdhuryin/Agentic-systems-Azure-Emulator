from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.correlation import new_correlation_id
from app.database import get_db
from app.error_utils import band_a_error_detail
from app.exceptions import BandAError
from app.ingestion.teams_inbound_adapter import TeamsInboundAdapter
from app.schemas import IngestionLogRow, IngestionLogsResponse
from app.services.ingestion_logs import list_ingestion_logs

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
    """Accept forwarded Microsoft Teams bot activities. Creates or qualifies a lead."""
    correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
    try:
        raw: dict[str, Any] = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Expected JSON body") from exc

    adapter = TeamsInboundAdapter(db)
    try:
        result = adapter.process_inbound_message(raw, correlation_id=correlation_id)
        return {"status": "accepted", **result}
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail=band_a_error_detail(exc)) from exc


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
    }
