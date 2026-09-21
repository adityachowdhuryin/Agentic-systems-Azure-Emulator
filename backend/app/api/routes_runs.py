from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.band_a.run_manager import RunManagerService
from app.database import Finding, InboundEvent, JournalTurn, Lead, QueueMessage, RuntimeEvent, Run, get_db
from app.repositories.base import EventRepository, QueueRepository, RunRepository
from app.schemas import InboundMailResponse, InboundTeamsResponse, QueueMessageResponse, RunResponse, RuntimeEventResponse
from app.services.inbound_mail import get_inbound_mail_for_run
from app.services.inbound_teams import get_inbound_teams_for_run

router = APIRouter(prefix="/api/v1", tags=["runs"])


@router.get("/runs", response_model=list[RunResponse])
def list_runs(tenant_id: str | None = None, db: Session = Depends(get_db)):
    return RunRepository(db).list_runs(tenant_id)


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.delete("/runs/{run_id}")
def delete_run(run_id: str, db: Session = Depends(get_db)):
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")

    lead_id = run.lead_id
    inbound_event_id = run.inbound_event_id

    db.query(RuntimeEvent).filter(RuntimeEvent.run_id == run_id).delete(synchronize_session=False)
    db.query(QueueMessage).filter(QueueMessage.run_id == run_id).delete(synchronize_session=False)
    db.query(JournalTurn).filter(JournalTurn.run_id == run_id).delete(synchronize_session=False)
    db.query(Finding).filter(Finding.run_id == run_id).delete(synchronize_session=False)
    db.query(Run).filter(Run.run_id == run_id).delete(synchronize_session=False)

    if inbound_event_id:
        still_referenced = (
            db.query(Run).filter(Run.inbound_event_id == inbound_event_id).first() is not None
        )
        if not still_referenced:
            db.query(InboundEvent).filter(InboundEvent.event_id == inbound_event_id).delete(
                synchronize_session=False
            )

    lead_deleted = False
    remaining_runs = db.query(Run).filter(Run.lead_id == lead_id).count()
    if remaining_runs == 0:
        db.query(InboundEvent).filter(InboundEvent.lead_id == lead_id).delete(synchronize_session=False)
        db.query(Lead).filter(Lead.lead_id == lead_id).delete(synchronize_session=False)
        lead_deleted = True

    db.commit()
    return {
        "status": "deleted",
        "run_id": run_id,
        "lead_id": lead_id,
        "lead_deleted": lead_deleted,
    }


@router.get("/runs/{run_id}/events", response_model=list[RuntimeEventResponse])
def get_run_events(run_id: str, db: Session = Depends(get_db)):
    return EventRepository(db).list_for_run(run_id)


@router.get("/runs/{run_id}/inbound-mail", response_model=InboundMailResponse)
def get_run_inbound_mail(run_id: str, db: Session = Depends(get_db)):
    mail = get_inbound_mail_for_run(db, run_id)
    if not mail:
        raise HTTPException(404, "No inbound mail content for this run")
    return InboundMailResponse(**mail)


@router.get("/runs/{run_id}/inbound-teams", response_model=InboundTeamsResponse)
def get_run_inbound_teams(run_id: str, db: Session = Depends(get_db)):
    msg = get_inbound_teams_for_run(db, run_id)
    if not msg:
        raise HTTPException(404, "No inbound Teams content for this run")
    return InboundTeamsResponse(**msg)


@router.get("/runs/{run_id}/queue-message", response_model=QueueMessageResponse | None)
def get_run_queue_message(run_id: str, db: Session = Depends(get_db)):
    msg = QueueRepository(db).get_by_run_id(run_id)
    return msg


@router.post("/runs/{run_id}/suspend")
def suspend_run(run_id: str, db: Session = Depends(get_db)):
    try:
        RunManagerService(db).suspend(run_id)
        db.commit()
        return {"status": "suspended", "run_id": run_id}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/runs/{run_id}/resume")
def resume_run(run_id: str, db: Session = Depends(get_db)):
    try:
        RunManagerService(db).resume(run_id)
        db.commit()
        return {"status": "resumed", "run_id": run_id}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
