from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.band_b.mock_consumer import mock_consumer
from app.database import get_db
from app.schemas import SchedulerStatusResponse
from app.services import sample_ingress
from app.services.admission_demos import SCENARIOS, run_scenario
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.services.seed import reset_demo

router = APIRouter(prefix="/api/v1", tags=["scheduler"])


class SampleIngestRequest(BaseModel):
    teams_ids: list[str] = Field(default_factory=list)
    zoho_ids: list[str] = Field(default_factory=list)


class TimerStartRequest(BaseModel):
    interval_seconds: int = Field(30, ge=5, le=3600)
    batch_teams: int = Field(1, ge=0, le=10)
    batch_zoho: int = Field(1, ge=0, le=10)
    # accept legacy single batch_size → apply to both channels
    batch_size: int | None = Field(None, ge=0, le=10)

    @model_validator(mode="after")
    def apply_legacy_batch_size(self):
        if self.batch_size is not None:
            self.batch_teams = self.batch_size
            self.batch_zoho = self.batch_size
        if self.batch_teams + self.batch_zoho < 1:
            raise ValueError("batch_teams + batch_zoho must be >= 1")
        return self


@router.get("/scheduler/samples")
def scheduler_samples():
    return sample_ingress.list_samples()


@router.post("/scheduler/ingest")
def scheduler_ingest(body: SampleIngestRequest, db: Session = Depends(get_db)):
    results = sample_ingress.ingest_by_ids(
        db,
        teams_ids=body.teams_ids,
        zoho_ids=body.zoho_ids,
    )
    return {
        "ingested": len([r for r in results if "error" not in r]),
        "results": results,
        "status": sample_ingress.status_dict(),
    }


@router.get("/scheduler/status", response_model=SchedulerStatusResponse)
def scheduler_status():
    raw = sample_ingress.status_dict()
    return SchedulerStatusResponse(**raw)


@router.post("/scheduler/timer/start", response_model=SchedulerStatusResponse)
def scheduler_timer_start(body: TimerStartRequest):
    raw = start_scheduler(
        interval_seconds=body.interval_seconds,
        batch_teams=body.batch_teams,
        batch_zoho=body.batch_zoho,
    )
    return SchedulerStatusResponse(**raw)


@router.post("/scheduler/timer/pause", response_model=SchedulerStatusResponse)
def scheduler_timer_pause():
    raw = stop_scheduler()
    return SchedulerStatusResponse(**raw)


@router.post("/scheduler/start", response_model=SchedulerStatusResponse)
def scheduler_start_compat():
    state = sample_ingress.get_player_state()
    raw = start_scheduler(
        interval_seconds=state.interval_seconds or 30,
        batch_teams=state.batch_teams if state.batch_teams is not None else 1,
        batch_zoho=state.batch_zoho if state.batch_zoho is not None else 1,
    )
    return SchedulerStatusResponse(**raw)


@router.post("/scheduler/stop", response_model=SchedulerStatusResponse)
def scheduler_stop_compat():
    return scheduler_timer_pause()


@router.post("/scheduler/reset")
def scheduler_reset(db: Session = Depends(get_db)):
    stop_scheduler()
    sample_ingress.reset_player_state()
    mock_consumer.stop()
    reset_demo(db)
    return {
        "status": "reset",
        "message": "Sample player reset; simulator/demo and sample-player data cleared; real live Zoho Mail / Teams preserved",
        "player": sample_ingress.status_dict(),
    }


@router.get("/scheduler/demos")
def scheduler_list_demos():
    catalog = [
        {
            "id": "invalid-auth",
            "title": "Invalid auth",
            "say": "Bad identity is rejected before a run exists.",
            "expect": "rejected, run_created=false",
        },
        {
            "id": "tenant-mismatch",
            "title": "Tenant mismatch",
            "say": "Token tenant must match the request tenant.",
            "expect": "rejected, no run",
        },
        {
            "id": "duplicate",
            "title": "Duplicate event_id",
            "say": "Same event_id twice is idempotent — same run_id, not a new ticket.",
            "expect": "duplicate=true, same run_id",
        },
        {
            "id": "active-run",
            "title": "Active run blocked",
            "say": "A second request while the lead still has a QUEUED run is rejected.",
            "expect": "ACTIVE_RUN_EXISTS; worker auto-stopped if needed",
        },
        {
            "id": "quota-exceeded",
            "title": "Quota exceeded",
            "say": "Tenant active-run budget is full — admission refuses new work.",
            "expect": "rejected, run_created=false",
        },
    ]
    return {"demos": [d for d in catalog if d["id"] in SCENARIOS]}


@router.post("/scheduler/demos/{scenario}")
def scheduler_run_demo(scenario: str, db: Session = Depends(get_db)):
    if scenario not in SCENARIOS:
        raise HTTPException(404, detail=f"Unknown demo scenario: {scenario}")
    return run_scenario(db, scenario)
