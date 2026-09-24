import logging
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.band_b.agent_loop import run_invoice_agent
from app.config import settings
from app.correlation import new_correlation_id
from app.database import SessionLocal, UseCase, get_db
from app.error_utils import band_a_error_detail
from app.exceptions import BandAError, ValidationError
from app.ingestion.teams_inbound_adapter import TeamsInboundAdapter
from app.repositories.base import RunRepository
from app.schemas import IngestionLogRow, IngestionLogsResponse
from app.services.ingestion_logs import list_ingestion_logs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["teams"])


def verify_teams_bridge_key(
    x_teams_bridge_key: Annotated[str | None, Header()] = None,
) -> None:
    if not x_teams_bridge_key or x_teams_bridge_key != settings.teams_bridge_key:
        raise HTTPException(status_code=401, detail="Invalid teams bridge key")


def _run_invoice_agent_for_run(run_id: str) -> None:
    """Background Band B so Teams bot can ack before Foundry finishes."""
    from app.database import QueueMessage

    db = SessionLocal()
    try:
        run = RunRepository(db).get_by_run_id(run_id)
        if not run:
            logger.error("Background invoice agent: run %s not found", run_id)
            return
        if run.use_case != UseCase.INVOICE_REVIEW.value:
            logger.error("Background invoice agent: run %s not invoice_review", run_id)
            return
        # Avoid double-processing if mock_consumer is also draining the queue
        db.query(QueueMessage).filter(QueueMessage.run_id == run_id).delete(synchronize_session=False)
        db.commit()
        run = RunRepository(db).get_by_run_id(run_id)
        run_invoice_agent(db, run)
        db.commit()
    except Exception:
        logger.exception("Background invoice agent failed for %s", run_id)
        db.rollback()
    finally:
        db.close()


@router.post("/webhooks/teams")
async def teams_inbound_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(verify_teams_bridge_key),
):
    """
    Accept forwarded Microsoft Teams bot activities.

    - Pack-shaped invoice JSON in the text (prose + JSON OK) → invoice_review + background Band B
    - Otherwise → invoice_review non-invoice path (Band B exception finding)
    - No live CASE-XX pack map (use dashboard Play CASE for fixtures)
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
        if result.get("use_case") == "invoice_review" and result.get("run_id") and not result.get("duplicate"):
            background_tasks.add_task(_run_invoice_agent_for_run, result["run_id"])
        return {"status": "accepted", **result}
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
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
        "invoice_case_tag": "Message CASE-01 … CASE-12 for invoice review",
    }
