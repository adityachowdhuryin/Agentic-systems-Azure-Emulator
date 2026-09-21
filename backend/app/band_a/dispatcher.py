from sqlalchemy.orm import Session

from app.database import LeadStatus, RunState, UseCase
from app.repositories.base import LeadRepository, QueueRepository, RunRepository
from app.security import add_runtime_event


class DispatcherService:
    def __init__(self, db: Session):
        self.db = db
        self.runs = RunRepository(db)
        self.leads = LeadRepository(db)
        self.queue = QueueRepository(db)

    def dispatch_async(self, run) -> object:
        run.dispatch_route = "async"
        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="DISPATCHER",
            component="dispatcher",
            action="async_selected",
            status="SUCCESS",
            message="ASYNC — qualification may take longer and caller does not wait",
            metadata={"dispatch_route": "async", "use_case": getattr(run, "use_case", None)},
        )

        self.runs.update_state(run, RunState.DISPATCHED.value)

        lead = self.leads.get_by_lead_id(run.lead_id)
        if lead:
            self.leads.update_status(lead, LeadStatus.QUALIFICATION_IN_PROGRESS.value)

        msg = self.queue.enqueue(
            run_id=run.run_id,
            tenant_id=run.tenant_id,
            lead_id=run.lead_id,
            source=run.source,
            payload={
                "run_id": run.run_id,
                "lead_id": run.lead_id,
                "tenant_id": run.tenant_id,
                "source": run.source,
                "use_case": getattr(run, "use_case", None),
            },
        )

        self.runs.update_state(run, RunState.QUEUED.value)

        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="MESSAGE_TRANSPORT",
            component="message_transport",
            action="enqueued",
            status="SUCCESS",
            message=f"Message {msg.message_id} enqueued to sales-lead-qualification",
        )

        return msg

    def dispatch_sync(self, run) -> dict:
        run.dispatch_route = "sync"
        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="DISPATCHER",
            component="dispatcher",
            action="sync_selected",
            status="SUCCESS",
            message="SYNC — runs in-process, answers on the same connection (05 Message Transport not used)",
            metadata={"dispatch_route": "sync", "use_case": getattr(run, "use_case", None)},
        )

        self.runs.update_state(run, RunState.DISPATCHED.value)

        lead = self.leads.get_by_lead_id(run.lead_id)
        if lead:
            self.leads.update_status(lead, LeadStatus.QUALIFICATION_IN_PROGRESS.value)

        if getattr(run, "use_case", None) == UseCase.INVOICE_REVIEW.value:
            from app.band_b.agent_loop import run_invoice_agent

            finding = run_invoice_agent(self.db, run)
            return {"run_id": run.run_id, "finding": finding, "dispatch_route": "sync"}

        result = {
            "run_id": run.run_id,
            "lead_id": run.lead_id,
            "qualification_status": "SYNC_DEMO_COMPLETE",
            "message": "Sync dispatch completed in-process without queue.",
        }

        self.runs.update_state(run, RunState.HANDED_OFF.value, "Sync handoff to Band B (no queue)")

        if lead:
            self.leads.update_status(lead, LeadStatus.QUALIFIED.value)

        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="DISPATCHER",
            component="dispatcher",
            action="sync_complete",
            status="SUCCESS",
            message="Sync path completed without Message Transport",
        )
        add_runtime_event(
            self.db,
            run_id=run.run_id,
            stage="BAND_B",
            component="dispatcher",
            action="handed_off",
            status="SUCCESS",
            message="Handed off to Band B on the sync path (Message Transport skipped).",
        )

        return result
