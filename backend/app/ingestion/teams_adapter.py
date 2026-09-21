import re
import uuid

from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.exceptions import ValidationError
from app.repositories.base import LeadRepository
from app.schemas import IngressPayload


LEAD_PATTERN = re.compile(r"qualify\s+lead\s+(LEAD-[\w-]+)", re.IGNORECASE)


class TeamsAdapter:
    def __init__(self, db: Session):
        self.db = db
        self.leads = LeadRepository(db)

    def parse_lead_id(self, message: str) -> str | None:
        match = LEAD_PATTERN.search(message.strip())
        return match.group(1).upper() if match else None

    def process_request(
        self,
        *,
        message: str,
        tenant_id: str,
        requested_by: str,
        lead_id: str | None,
        token_claims: dict,
        correlation_id: str,
        force_sync: bool = False,
        extra_payload: dict | None = None,
        event_id: str | None = None,
    ) -> dict:
        parsed_lead = lead_id or self.parse_lead_id(message)
        if not parsed_lead:
            raise ValidationError("Could not parse lead ID from message. Use: Qualify lead LEAD-xxxxx")

        lead = self.leads.get_by_lead_id(parsed_lead)
        if not lead:
            raise ValidationError(f"Lead {parsed_lead} not found")

        if lead.tenant_id != tenant_id:
            raise ValidationError(f"Lead {parsed_lead} belongs to tenant {lead.tenant_id}, not {tenant_id}")

        event_id = event_id or f"teams-{uuid.uuid4().hex[:8]}"
        inner = {"message": message, **(extra_payload or {})}
        payload = {
            "source": "teams",
            "event_type": "qualify_lead_request",
            "event_id": event_id,
            "tenant_id": tenant_id,
            "lead_id": parsed_lead,
            "requested_by": requested_by,
            "payload": inner,
        }
        ingress = IngressPayload(**payload)
        orchestrator = BandAOrchestrator(self.db)
        return orchestrator.process(
            ingress,
            raw_payload=payload,
            token_claims=token_claims,
            correlation_id=correlation_id,
            force_sync=force_sync,
        )
