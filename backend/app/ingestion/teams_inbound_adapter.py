import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.config import settings
from app.ingestion.teams_adapter import TeamsAdapter
from app.repositories.base import LeadRepository
from app.schemas import IngressPayload, LeadCreate


def _str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""


def parse_teams_inbound(raw: dict[str, Any]) -> dict[str, str]:
    nested_from = raw.get("from") if isinstance(raw.get("from"), dict) else {}
    channel_data = raw.get("channelData") if isinstance(raw.get("channelData"), dict) else {}
    team = channel_data.get("team") if isinstance(channel_data.get("team"), dict) else {}
    channel = channel_data.get("channel") if isinstance(channel_data.get("channel"), dict) else {}
    conversation = raw.get("conversation") if isinstance(raw.get("conversation"), dict) else {}

    text = _str(raw.get("text") or raw.get("message") or raw.get("teams_text"))
    from_name = _str(
        raw.get("from_name")
        or raw.get("teams_from")
        or nested_from.get("name")
        or nested_from.get("aadObjectId")
    )
    from_id = _str(raw.get("from_id") or nested_from.get("id") or nested_from.get("aadObjectId"))
    channel_id = _str(raw.get("channel_id") or raw.get("teams_channel"))
    if not channel_id:
        channel_id = _str(channel.get("id") or channel.get("name") or raw.get("channelId"))
    team_id = _str(raw.get("team_id") or team.get("id") or team.get("name"))
    conversation_id = _str(raw.get("conversation_id") or conversation.get("id"))
    activity_id = _str(raw.get("activity_id") or raw.get("id"))

    return {
        "text": text,
        "from_name": from_name or "Teams User",
        "from_id": from_id,
        "channel_id": channel_id,
        "team_id": team_id,
        "conversation_id": conversation_id,
        "activity_id": activity_id,
    }


def _teams_fields(parsed: dict[str, str]) -> dict[str, str]:
    return {
        "teams_from": parsed["from_name"],
        "teams_from_id": parsed["from_id"],
        "teams_text": parsed["text"],
        "teams_channel": parsed["channel_id"],
        "teams_team": parsed["team_id"],
        "conversation_id": parsed["conversation_id"],
        "activity_id": parsed["activity_id"],
        "message": parsed["text"],
    }


def _event_id(parsed: dict[str, str]) -> str:
    if parsed["activity_id"]:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "-", parsed["activity_id"])[:48]
        return f"teams-{safe}"
    return f"teams-{uuid.uuid4().hex[:12]}"


def _lead_from_message(parsed: dict[str, str], *, tenant_id: str) -> LeadCreate:
    text = parsed["text"] or "Inbound Teams message"
    contact = parsed["from_name"][:128]
    slug = re.sub(r"[^a-zA-Z0-9]+", "", contact)[:12].lower() or "teams"
    return LeadCreate(
        tenant_id=tenant_id,
        company_name="Teams Inquiry",
        industry="Unknown",
        employee_count=0,
        requirement=text[:500],
        budget=0,
        contact_name=contact,
        contact_role="Teams User",
        email=f"{slug}@teams.local",
        source="Teams",
    )


class TeamsInboundAdapter:
    def __init__(self, db: Session):
        self.db = db
        self.leads = LeadRepository(db)
        self.teams = TeamsAdapter(db)

    def process_inbound_message(
        self,
        raw: dict[str, Any],
        *,
        correlation_id: str,
    ) -> dict[str, Any]:
        parsed = parse_teams_inbound(raw)
        extra = _teams_fields(parsed)
        if _str(raw.get("demo_origin")):
            extra["demo_origin"] = _str(raw.get("demo_origin"))
        tenant_id = settings.teams_tenant_id
        requested_by = parsed["from_id"] or parsed["from_name"] or "teams-user"
        event_id = _event_id(parsed)
        token_claims = {
            "sub": requested_by,
            "tenant_id": tenant_id,
            "role": "sales-user",
            "aud": settings.jwt_audience,
        }

        parsed_lead = self.teams.parse_lead_id(parsed["text"]) if parsed["text"] else None
        existing = self.leads.get_by_lead_id(parsed_lead) if parsed_lead else None

        if existing and existing.tenant_id == tenant_id:
            result = self.teams.process_request(
                message=parsed["text"],
                tenant_id=tenant_id,
                requested_by=requested_by,
                lead_id=existing.lead_id,
                token_claims=token_claims,
                correlation_id=correlation_id,
                force_sync=True,
                extra_payload=extra,
                event_id=event_id,
            )
            return {
                "lead_id": existing.lead_id,
                "run_id": result.get("run_id"),
                "state": result.get("state"),
                "event_id": event_id,
                "correlation_id": correlation_id,
                "duplicate": result.get("duplicate", False),
                "rejected": result.get("rejected", False),
                "created_lead": False,
                "parsed_teams": parsed,
            }

        lead = self.leads.create(_lead_from_message(parsed, tenant_id=tenant_id))
        payload = {
            "source": "teams",
            "event_type": "qualify_lead_request",
            "event_id": event_id,
            "tenant_id": tenant_id,
            "lead_id": lead.lead_id,
            "requested_by": requested_by,
            "payload": extra,
        }
        ingress = IngressPayload(**payload)
        orchestrator = BandAOrchestrator(self.db)
        result = orchestrator.process(
            ingress,
            raw_payload=payload,
            token_claims=token_claims,
            correlation_id=correlation_id,
            force_sync=True,
        )
        return {
            "lead_id": lead.lead_id,
            "run_id": result.get("run_id"),
            "state": result.get("state"),
            "event_id": event_id,
            "correlation_id": correlation_id,
            "duplicate": result.get("duplicate", False),
            "rejected": result.get("rejected", False),
            "created_lead": True,
            "parsed_teams": parsed,
        }
