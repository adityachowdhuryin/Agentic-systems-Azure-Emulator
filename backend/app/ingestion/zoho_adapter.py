import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.repositories.base import LeadRepository
from app.schemas import IngressPayload, LeadCreate
from app.security import sign_zoho_payload


class ZohoAdapter:
    def __init__(self, db: Session):
        self.db = db
        self.leads = LeadRepository(db)

    def create_lead_and_webhook(
        self,
        data: LeadCreate,
        *,
        token_claims: dict,
        correlation_id: str,
    ) -> dict[str, Any]:
        lead = self.leads.create(data)
        event_id = f"zoho-{uuid.uuid4().hex[:10]}"
        payload = {
            "source": "zoho",
            "event_type": "lead_created",
            "event_id": event_id,
            "tenant_id": data.tenant_id,
            "lead_id": lead.lead_id,
            "payload": {
                "company_name": lead.company_name,
                "industry": lead.industry,
                "employee_count": lead.employee_count,
                "requirement": lead.requirement,
                "budget": lead.budget,
                "contact_name": lead.contact_name,
                "contact_role": lead.contact_role,
                "email": lead.email,
            },
        }
        signature = sign_zoho_payload(payload)
        ingress = IngressPayload(**payload)
        orchestrator = BandAOrchestrator(self.db)
        result = orchestrator.process(
            ingress,
            raw_payload=payload,
            token_claims=token_claims,
            correlation_id=correlation_id,
            zoho_signature=signature,
        )
        return {
            "lead": lead,
            "event_id": event_id,
            "signature": signature,
            **result,
        }

    def send_webhook_for_lead(
        self,
        lead_id: str,
        *,
        token_claims: dict,
        correlation_id: str,
    ) -> dict[str, Any]:
        lead = self.leads.get_by_lead_id(lead_id)
        if not lead:
            raise ValueError(f"Lead {lead_id} not found")
        event_id = f"zoho-{uuid.uuid4().hex[:10]}"
        payload = {
            "source": "zoho",
            "event_type": "lead_created",
            "event_id": event_id,
            "tenant_id": lead.tenant_id,
            "lead_id": lead.lead_id,
            "payload": {
                "company_name": lead.company_name,
                "industry": lead.industry,
                "employee_count": lead.employee_count,
                "requirement": lead.requirement,
                "budget": lead.budget,
                "contact_name": lead.contact_name,
                "contact_role": lead.contact_role,
                "email": lead.email,
            },
        }
        signature = sign_zoho_payload(payload)
        ingress = IngressPayload(**payload)
        orchestrator = BandAOrchestrator(self.db)
        result = orchestrator.process(
            ingress,
            raw_payload=payload,
            token_claims=token_claims,
            correlation_id=correlation_id,
            zoho_signature=signature,
        )
        return {"event_id": event_id, "signature": signature, **result}
