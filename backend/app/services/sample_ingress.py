from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.correlation import new_correlation_id
from app.exceptions import BandAError
from app.ingestion.teams_inbound_adapter import TeamsInboundAdapter
from app.ingestion.zoho_mail_adapter import ZohoMailAdapter

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLES_ROOT = REPO_ROOT / "samples"


@dataclass
class SampleItem:
    id: str
    channel: str  # teams | zoho
    title: str
    preview: str
    raw: dict[str, Any]


@dataclass
class PlayerState:
    used_teams: set[str] = field(default_factory=set)
    used_zoho: set[str] = field(default_factory=set)
    enabled: bool = False
    interval_seconds: int = 30
    batch_teams: int = 1
    batch_zoho: int = 1
    next_run_at: datetime | None = None
    last_tick_at: datetime | None = None
    last_tick_summary: dict[str, Any] | None = None
    pause_reason: str | None = None


_state = PlayerState()


def get_player_state() -> PlayerState:
    return _state


def samples_dir(channel: str) -> Path:
    return SAMPLES_ROOT / channel


def _load_channel(channel: str) -> list[SampleItem]:
    folder = samples_dir(channel)
    if not folder.is_dir():
        return []
    items: list[SampleItem] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        sample_id = str(data.get("id") or path.stem)
        title = str(data.get("title") or sample_id)
        if channel == "teams":
            preview = str(data.get("text") or "")[:120]
        else:
            preview = str(data.get("subject") or data.get("body") or "")[:120]
        items.append(
            SampleItem(
                id=sample_id,
                channel=channel,
                title=title,
                preview=preview,
                raw=data,
            )
        )
    return items


def list_samples() -> dict[str, list[dict[str, Any]]]:
    state = _state
    teams = []
    for item in _load_channel("teams"):
        teams.append(
            {
                "id": item.id,
                "channel": "teams",
                "title": item.title,
                "preview": item.preview,
                "used": item.id in state.used_teams,
            }
        )
    zoho = []
    for item in _load_channel("zoho"):
        zoho.append(
            {
                "id": item.id,
                "channel": "zoho",
                "title": item.title,
                "preview": item.preview,
                "used": item.id in state.used_zoho,
            }
        )
    return {"teams": teams, "zoho": zoho}


def unused_samples(channel: str) -> list[SampleItem]:
    used = _state.used_teams if channel == "teams" else _state.used_zoho
    return [s for s in _load_channel(channel) if s.id not in used]


def remaining_counts() -> tuple[int, int]:
    return len(unused_samples("teams")), len(unused_samples("zoho"))


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


def ingest_teams_sample(db: Session, item: SampleItem) -> dict[str, Any]:
    suffix = _unique_suffix()
    payload = {
        "text": item.raw.get("text") or item.title,
        "from_name": item.raw.get("from_name") or "Sample User",
        "activity_id": f"{item.id}-{suffix}",
        "channel_id": "sample-ingress",
        "conversation_id": f"sample-conv-{item.id}",
        "demo_origin": "sample_player",
    }
    adapter = TeamsInboundAdapter(db)
    result = adapter.process_inbound_message(payload, correlation_id=new_correlation_id())
    return {"channel": "teams", "sample_id": item.id, **result}


def ingest_zoho_sample(db: Session, item: SampleItem) -> dict[str, Any]:
    suffix = _unique_suffix()
    payload = {
        "from": item.raw.get("from") or "sample@example.com",
        "subject": item.raw.get("subject") or item.title,
        "body": item.raw.get("body") or "",
        "messageId": f"{item.id}-{suffix}",
        "to": "inbox@band-a.example",
        "demo_origin": "sample_player",
    }
    adapter = ZohoMailAdapter(db)
    result = adapter.process_inbound_mail(payload, correlation_id=new_correlation_id())
    return {"channel": "zoho", "sample_id": item.id, **result}


def _safe_ingest(db: Session, channel: str, item: SampleItem) -> dict[str, Any]:
    try:
        if channel == "teams":
            result = ingest_teams_sample(db, item)
        else:
            result = ingest_zoho_sample(db, item)
        db.commit()
        if channel == "teams":
            _state.used_teams.add(item.id)
        else:
            _state.used_zoho.add(item.id)
        return result
    except BandAError as exc:
        db.rollback()
        logger.warning("Sample ingest BandAError %s: %s", item.id, exc.message)
        return {
            "channel": channel,
            "sample_id": item.id,
            "error": exc.code,
            "message": exc.message,
            "existing_run_id": exc.existing_run_id,
        }
    except Exception as exc:
        db.rollback()
        logger.exception("Sample ingest failed for %s", item.id)
        return {
            "channel": channel,
            "sample_id": item.id,
            "error": "ingest_failed",
            "message": str(exc),
        }


def ingest_by_ids(
    db: Session,
    *,
    teams_ids: list[str],
    zoho_ids: list[str],
) -> list[dict[str, Any]]:
    teams_map = {s.id: s for s in _load_channel("teams")}
    zoho_map = {s.id: s for s in _load_channel("zoho")}
    results: list[dict[str, Any]] = []
    for sid in teams_ids:
        item = teams_map.get(sid)
        if not item:
            results.append({"channel": "teams", "sample_id": sid, "error": "not_found"})
            continue
        results.append(_safe_ingest(db, "teams", item))
    for sid in zoho_ids:
        item = zoho_map.get(sid)
        if not item:
            results.append({"channel": "zoho", "sample_id": sid, "error": "not_found"})
            continue
        results.append(_safe_ingest(db, "zoho", item))
    return results


def can_fill_batch(*, batch_teams: int, batch_zoho: int) -> bool:
    if batch_teams + batch_zoho < 1:
        return False
    rem_t, rem_z = remaining_counts()
    if batch_teams > 0 and rem_t < batch_teams:
        return False
    if batch_zoho > 0 and rem_z < batch_zoho:
        return False
    return True


def run_timer_tick(db: Session) -> dict[str, Any]:
    """Ingest next batch_teams + batch_zoho. Pause when a positive quota can't be filled."""
    state = _state
    n_t = max(0, int(state.batch_teams))
    n_z = max(0, int(state.batch_zoho))
    if not can_fill_batch(batch_teams=n_t, batch_zoho=n_z):
        state.enabled = False
        state.pause_reason = "samples_exhausted"
        state.next_run_at = None
        summary = {
            "status": "paused",
            "reason": "samples_exhausted",
            "results": [],
            "remaining_teams": remaining_counts()[0],
            "remaining_zoho": remaining_counts()[1],
            "ingested_teams": 0,
            "ingested_zoho": 0,
        }
        state.last_tick_at = datetime.now(timezone.utc)
        state.last_tick_summary = summary
        return summary

    teams_batch = unused_samples("teams")[:n_t] if n_t else []
    zoho_batch = unused_samples("zoho")[:n_z] if n_z else []
    results: list[dict[str, Any]] = []
    for item in teams_batch:
        results.append(_safe_ingest(db, "teams", item))
    for item in zoho_batch:
        results.append(_safe_ingest(db, "zoho", item))

    ingested_teams = len([r for r in results if r.get("channel") == "teams" and "error" not in r])
    ingested_zoho = len([r for r in results if r.get("channel") == "zoho" and "error" not in r])

    rem_t, rem_z = remaining_counts()
    exhausted = not can_fill_batch(batch_teams=n_t, batch_zoho=n_z)
    if exhausted:
        state.enabled = False
        state.pause_reason = "samples_exhausted"
        state.next_run_at = None

    summary = {
        "status": "ok" if not exhausted else "paused",
        "reason": "samples_exhausted" if exhausted else None,
        "results": results,
        "remaining_teams": rem_t,
        "remaining_zoho": rem_z,
        "ingested_teams": ingested_teams,
        "ingested_zoho": ingested_zoho,
    }
    state.last_tick_at = datetime.now(timezone.utc)
    state.last_tick_summary = summary
    if state.enabled:
        state.next_run_at = datetime.now(timezone.utc) + timedelta(seconds=state.interval_seconds)
    return summary


def reset_player_state() -> None:
    global _state
    _state = PlayerState(
        interval_seconds=_state.interval_seconds,
        batch_teams=_state.batch_teams,
        batch_zoho=_state.batch_zoho,
    )


def status_dict() -> dict[str, Any]:
    rem_t, rem_z = remaining_counts()
    next_run = _state.next_run_at
    seconds_remaining = None
    if next_run and _state.enabled:
        seconds_remaining = max(
            0, int((next_run - datetime.now(timezone.utc)).total_seconds())
        )
    return {
        "enabled": _state.enabled,
        "interval_seconds": _state.interval_seconds,
        "batch_teams": _state.batch_teams,
        "batch_zoho": _state.batch_zoho,
        # back-compat alias
        "batch_size": max(_state.batch_teams, _state.batch_zoho),
        "next_run_at": next_run,
        "seconds_remaining": seconds_remaining,
        "remaining_teams": rem_t,
        "remaining_zoho": rem_z,
        "used_teams": len(_state.used_teams),
        "used_zoho": len(_state.used_zoho),
        "last_tick_at": _state.last_tick_at,
        "last_tick": _state.last_tick_summary,
        "pause_reason": _state.pause_reason,
        "last_run_at": _state.last_tick_at,
        "last_run_count": (
            (_state.last_tick_summary or {}).get("ingested_teams", 0)
            + (_state.last_tick_summary or {}).get("ingested_zoho", 0)
        )
        if _state.last_tick_summary
        else 0,
    }
