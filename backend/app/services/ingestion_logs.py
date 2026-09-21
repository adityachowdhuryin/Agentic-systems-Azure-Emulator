from __future__ import annotations

from sqlalchemy.orm import Session

from app.database import Lead, Run
from app.repositories.base import EventRepository, LeadRepository
from app.services.inbound_teams import get_inbound_teams_for_run
from app.timeutils import to_utc_iso

STAGE_ORDER = [
    ("INGRESS", "Ingress"),
    ("ADMISSION", "Admission"),
    ("RUN_MANAGER", "Run"),
    ("DISPATCHER", "Dispatch"),
    ("MESSAGE_TRANSPORT", "Transport"),
]

STATE_TO_PHASE = {
    "QUEUED": "queued",
    "HANDED_OFF": "done",
    "REJECTED": "rejected",
    "FAILED": "failed",
    "SUSPENDED": "running",
    "RECEIVED": "running",
    "ADMITTED": "running",
    "DISPATCHED": "running",
}


def _truncate(text: str, limit: int = 80) -> str:
    text = (text or "").strip().replace("\n", " ")
    if not text:
        return "—"
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _band_a_stage(events: list) -> str:
    reached = {e.stage for e in events if getattr(e, "status", "") != "FAILED"}
    last = "—"
    for stage_id, short in STAGE_ORDER:
        if stage_id in reached:
            last = short
    # If any failed admission/rejection, still show furthest successful stage
    return last


def _phase(run: Run) -> str:
    return STATE_TO_PHASE.get(run.state, run.state.lower() if run.state else "—")


def _route(events: list) -> str:
    actions = {e.action for e in events}
    if "enqueued" in actions or "async_selected" in actions:
        return "async"
    if "sync_selected" in actions or "sync_complete" in actions:
        return "sync"
    return "—"


def _note(run: Run, events: list) -> str:
    if run.status_reason and run.status_reason.strip():
        return _truncate(run.status_reason, 100)
    if events:
        last = events[-1]
        if last.message:
            return _truncate(last.message, 100)
    return "—"


def list_ingestion_logs(
    db: Session,
    *,
    source: str = "teams",
    limit: int = 25,
) -> list[dict]:
    """Build ingestion-log rows for real inbound channels (Teams for now)."""
    if source != "teams":
        return []

    lead_ids = [
        row[0]
        for row in db.query(Lead.lead_id).filter(Lead.source == "Teams").all()
    ]
    if not lead_ids:
        return []

    runs = (
        db.query(Run)
        .filter(Run.lead_id.in_(lead_ids))
        .order_by(Run.created_at.desc())
        .limit(max(1, min(limit, 50)))
        .all()
    )

    events_repo = EventRepository(db)
    leads_repo = LeadRepository(db)
    rows: list[dict] = []

    for run in runs:
        events = events_repo.list_for_run(run.run_id)
        inbound = get_inbound_teams_for_run(db, run.run_id)
        lead = leads_repo.get_by_lead_id(run.lead_id)

        topic = "—"
        if inbound and inbound.get("teams_text"):
            topic = _truncate(inbound["teams_text"])
        elif lead and lead.requirement:
            topic = _truncate(lead.requirement)

        rows.append(
            {
                "run_id": run.run_id,
                "lead_id": run.lead_id,
                "tenant_id": run.tenant_id or "—",
                "owner": run.owner or "—",
                "topic": topic,
                "source": "Teams",
                "route": _route(events),
                "band_a_stage": _band_a_stage(events),
                "phase": _phase(run),
                "state": run.state or "—",
                "spend": None,
                "received_at": to_utc_iso(run.created_at),
                "note": _note(run, events),
            }
        )

    return rows
