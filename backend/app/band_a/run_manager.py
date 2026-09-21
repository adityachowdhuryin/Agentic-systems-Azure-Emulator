from sqlalchemy.orm import Session

from app.config import settings
from app.database import LeadStatus, RunState, UseCase
from app.repositories.base import LeadRepository, RunRepository
from app.security import add_runtime_event


class RunManagerService:
    def __init__(self, db: Session):
        self.db = db
        self.runs = RunRepository(db)
        self.leads = LeadRepository(db)

    def create_run(
        self,
        normalized: dict,
        *,
        token_claims: dict,
        correlation_id: str,
    ):
        owner = normalized.get("requested_by") or token_claims.get("sub", "system")
        quota = settings.tenant_quota(normalized["tenant_id"])
        inner = normalized.get("payload") or {}
        use_case = inner.get("use_case") or UseCase.SALES_LEAD.value

        run = self.runs.create_run(
            tenant_id=normalized["tenant_id"],
            source=normalized["source"],
            trigger_type=normalized["trigger_type"],
            lead_id=normalized["lead_id"],
            owner=owner,
            budget_limit=quota,
            correlation_id=correlation_id,
            inbound_event_id=normalized["inbound_event_id"],
            use_case=use_case,
            document_ref=inner.get("document_ref"),
            supplier_id=inner.get("supplier_id"),
            arrival_source=inner.get("arrival_source"),
            budget_turns=int(inner.get("budget_turns") or settings.invoice_budget_turns),
            budget_usd_cents=int(inner.get("budget_usd_cents") or settings.invoice_budget_usd_cents),
            budget_seconds=int(inner.get("budget_seconds") or settings.invoice_budget_seconds),
        )

        lead = self.leads.get_by_lead_id(normalized["lead_id"])
        if lead and lead.status == LeadStatus.NEW.value:
            self.leads.update_status(lead, LeadStatus.PENDING_QUALIFICATION.value)

        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="RUN_MANAGER",
            component="run_manager",
            action="run_created",
            status="SUCCESS",
            message=f"Run {run.run_id} created with state ADMITTED",
        )

        return run

    def suspend(self, run_id: str) -> None:
        run = self.runs.get_by_run_id(run_id)
        if not run:
            raise ValueError("Run not found")
        if run.state == RunState.HANDED_OFF.value:
            raise ValueError("Cannot suspend handed-off run")
        run.suspend_requested = True
        self.runs.update_state(run, RunState.SUSPENDED.value, "Suspended by user")
        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="RUN_MANAGER",
            component="run_manager",
            action="suspend",
            status="SUCCESS",
            message="Run suspended",
        )

    def resume(self, run_id: str) -> None:
        run = self.runs.get_by_run_id(run_id)
        if not run:
            raise ValueError("Run not found")
        run.suspend_requested = False
        run.resume_token = f"RES-{run.run_id[-6:]}"
        self.runs.update_state(run, RunState.QUEUED.value, "Resumed by user")
        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="RUN_MANAGER",
            component="run_manager",
            action="resume",
            status="SUCCESS",
            message="Run resumed",
        )
