import json

from app.repositories.base import EventRepository, LeadRepository, RunRepository
from app.timeutils import to_utc_iso


def get_inbound_teams_for_run(db, run_id: str) -> dict | None:
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        return None

    inbound = EventRepository(db).get_by_event_id(run.inbound_event_id)
    if not inbound:
        return None

    try:
        stored = json.loads(inbound.payload_json)
    except json.JSONDecodeError:
        stored = {}

    inner = stored.get("payload") if isinstance(stored.get("payload"), dict) else {}

    teams_from = inner.get("teams_from") or stored.get("requested_by") or ""
    teams_text = inner.get("teams_text") or inner.get("message") or ""
    teams_channel = inner.get("teams_channel") or ""
    conversation_id = inner.get("conversation_id") or ""
    activity_id = inner.get("activity_id") or stored.get("event_id") or inbound.event_id

    if not teams_text and not teams_from:
        lead = LeadRepository(db).get_by_lead_id(run.lead_id)
        if lead and lead.source == "Teams":
            teams_from = lead.contact_name or ""
            teams_text = lead.requirement or ""

    if inbound.source != "teams" and not any([teams_from, teams_text, teams_channel]):
        return None

    if inbound.source != "teams":
        return None

    return {
        "run_id": run.run_id,
        "lead_id": run.lead_id,
        "source": inbound.source,
        "event_id": inbound.event_id,
        "teams_from": teams_from,
        "teams_text": teams_text,
        "teams_channel": teams_channel,
        "conversation_id": conversation_id,
        "activity_id": activity_id,
        "received_at": to_utc_iso(inbound.received_at) if inbound.received_at else None,
    }
