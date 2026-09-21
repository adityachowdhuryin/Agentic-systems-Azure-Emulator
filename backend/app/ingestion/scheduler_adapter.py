import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.database import LeadStatus
from app.repositories.base import LeadRepository
from app.schemas import IngressPayload


class SchedulerAdapter:
    def __init__(self, db: Session):
        self.db = db
        self.leads = LeadRepository(db)
        self.last_run_at: datetime | None = None
        self.last_run_count: int = 0

    def find_pending_leads(self, tenant_id: str | None = None) -> list:
        leads = self.leads.list_leads(tenant_id)
        pending = []
        for lead in leads:
            if lead.status not in {LeadStatus.NEW.value, LeadStatus.PENDING_QUALIFICATION.value}:
                continue
            active = self.leads.get_active_run_for_lead(lead.lead_id)
            if active:
                continue
            pending.append(lead)
        return pending

    def run_sweep(
        self,
        *,
        token_claims: dict,
        correlation_id_prefix: str,
        tenant_id: str | None = None,
    ) -> list[dict]:
        pending = self.find_pending_leads(tenant_id)
        results = []
        for lead in pending:
            event_id = f"schedule-{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')}-{uuid.uuid4().hex[:4]}"
            payload = {
                "source": "scheduler",
                "event_type": "scheduled_qualification",
                "event_id": event_id,
                "tenant_id": lead.tenant_id,
                "lead_id": lead.lead_id,
                "payload": {"reason": "pending qualification sweep"},
            }
            ingress = IngressPayload(**payload)
            orchestrator = BandAOrchestrator(self.db)
            cid = f"{correlation_id_prefix}-{lead.lead_id[-4:]}"
            result = orchestrator.process(
                ingress,
                raw_payload=payload,
                token_claims=token_claims,
                correlation_id=cid,
            )
            results.append(result)

        self.last_run_at = datetime.utcnow()
        self.last_run_count = len(results)
        return results
