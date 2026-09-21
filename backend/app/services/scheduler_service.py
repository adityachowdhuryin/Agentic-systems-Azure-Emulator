import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import HTTPException

from app.database import SessionLocal
from app.services import sample_ingress

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scheduled_job() -> None:
    db = SessionLocal()
    try:
        state = sample_ingress.get_player_state()
        if not state.enabled:
            return
        summary = sample_ingress.run_timer_tick(db)
        logger.info("Sample ingress tick: %s", summary.get("status"))
        if not state.enabled:
            stop_scheduler()
            return
        state.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=state.interval_seconds)
    except Exception:
        logger.exception("Sample ingress timer job failed")
    finally:
        db.close()


def start_scheduler(
    *,
    interval_seconds: int,
    batch_teams: int,
    batch_zoho: int,
) -> dict:
    global _scheduler
    state = sample_ingress.get_player_state()
    state.interval_seconds = max(5, int(interval_seconds))
    state.batch_teams = max(0, int(batch_teams))
    state.batch_zoho = max(0, int(batch_zoho))
    state.pause_reason = None

    if state.batch_teams + state.batch_zoho < 1:
        raise HTTPException(status_code=422, detail="batch_teams + batch_zoho must be >= 1")

    if not sample_ingress.can_fill_batch(
        batch_teams=state.batch_teams,
        batch_zoho=state.batch_zoho,
    ):
        state.enabled = False
        state.pause_reason = "samples_exhausted"
        state.next_run_at = None
        return sample_ingress.status_dict()

    state.enabled = True
    state.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=state.interval_seconds)

    if _scheduler is not None:
        if _scheduler.running:
            _scheduler.shutdown(wait=False)
        _scheduler = None

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _scheduled_job,
        trigger=IntervalTrigger(seconds=state.interval_seconds),
        id="sample_ingress_tick",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "Sample ingress timer started: every %ss, teams=%s zoho=%s",
        state.interval_seconds,
        state.batch_teams,
        state.batch_zoho,
    )
    return sample_ingress.status_dict()


def stop_scheduler() -> dict:
    global _scheduler
    state = sample_ingress.get_player_state()
    state.enabled = False
    state.next_run_at = None
    if state.pause_reason is None:
        state.pause_reason = "paused"
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Sample ingress timer stopped")
    _scheduler = None
    return sample_ingress.status_dict()


def is_scheduler_running() -> bool:
    return sample_ingress.get_player_state().enabled
