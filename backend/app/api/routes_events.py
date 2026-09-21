from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.band_a.message_transport import MessageTransportService
from app.band_b.mock_consumer import mock_consumer
from app.database import (
    ACTIVE_RUN_STATES,
    Lead,
    QueueMessage,
    QueueMessageStatus,
    Run,
    RunState,
    RuntimeEvent,
    get_db,
)
from app.schemas import MetricsSummary, QueueMessageResponse, QueueStatusResponse
from app.services.seed import reset_demo

router = APIRouter(prefix="/api/v1", tags=["queue"])

SOURCE_FILTER_MAP = {
    "all": None,
    "zoho_mail": "Zoho Mail",
    "teams": "Teams",
}


@router.get("/queue/status", response_model=QueueStatusResponse)
def queue_status(db: Session = Depends(get_db)):
    svc = MessageTransportService(db)
    return QueueStatusResponse(**svc.get_status(mock_consumer.is_running))


@router.get("/queue/messages", response_model=list[QueueMessageResponse])
def queue_messages(status: str | None = None, db: Session = Depends(get_db)):
    return MessageTransportService(db).list_messages(status)


@router.post("/queue/worker/start")
def start_worker():
    mock_consumer.start()
    return {"worker_running": True}


@router.post("/queue/worker/stop")
def stop_worker():
    mock_consumer.stop()
    return {"worker_running": False}


@router.get("/metrics/summary", response_model=MetricsSummary)
def metrics_summary(
    source_filter: str = Query("all", pattern="^(all|zoho_mail|teams)$"),
    db: Session = Depends(get_db),
):
    lead_source = SOURCE_FILTER_MAP[source_filter]

    lead_q = db.query(Lead)
    if lead_source:
        lead_q = lead_q.filter(Lead.source == lead_source)

    # Separate query objects — chaining .filter on a shared query mutates incorrectly after count
    def scoped_runs():
        q = db.query(Run)
        if lead_source:
            q = q.join(Lead, Lead.lead_id == Run.lead_id).filter(Lead.source == lead_source)
        return q

    total_leads = lead_q.count()
    active_runs = scoped_runs().filter(Run.state.in_(list(ACTIVE_RUN_STATES))).count()
    completed = scoped_runs().filter(Run.state == RunState.HANDED_OFF.value).count()
    failed = scoped_runs().filter(Run.state == RunState.FAILED.value).count()

    queued_q = db.query(func.count(QueueMessage.id)).filter(
        QueueMessage.status == QueueMessageStatus.PENDING.value,
    )
    if lead_source:
        queued_q = queued_q.join(Lead, Lead.lead_id == QueueMessage.lead_id).filter(
            Lead.source == lead_source
        )
    queued = queued_q.scalar() or 0

    rejected_q = db.query(func.count(RuntimeEvent.id)).filter(RuntimeEvent.action == "rejected")
    if lead_source:
        rejected_q = (
            rejected_q.join(Run, Run.run_id == RuntimeEvent.run_id)
            .join(Lead, Lead.lead_id == Run.lead_id)
            .filter(Lead.source == lead_source)
        )
    rejected = rejected_q.scalar() or 0

    return MetricsSummary(
        total_leads=total_leads,
        active_runs=active_runs,
        queued_messages=queued,
        completed_handoffs=completed,
        rejected_requests=rejected,
        failed_runs=failed,
        source_filter=source_filter,
    )


@router.get("/health")
def health():
    return {"status": "ok", "service": "band-a-local"}


@router.post("/demo/reset")
def demo_reset(db: Session = Depends(get_db)):
    mock_consumer.stop()
    reset_demo(db)
    return {
        "status": "reset",
        "message": "Simulator/demo and sample-player data cleared; real live Zoho Mail and Teams inbound data preserved",
        "worker_running": False,
    }
