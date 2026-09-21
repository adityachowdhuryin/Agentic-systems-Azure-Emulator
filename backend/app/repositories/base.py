import json
import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import (
    ACTIVE_RUN_STATES,
    InboundEvent,
    Lead,
    LeadStatus,
    QueueMessage,
    QueueMessageStatus,
    Run,
    RunState,
    RuntimeEvent,
)
from app.schemas import LeadCreate


class LeadRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_lead_id(self, lead_id: str) -> Lead | None:
        return self.db.query(Lead).filter(Lead.lead_id == lead_id).first()

    def list_leads(self, tenant_id: str | None = None) -> list[Lead]:
        q = self.db.query(Lead)
        if tenant_id:
            q = q.filter(Lead.tenant_id == tenant_id)
        return q.order_by(Lead.created_at.desc()).all()

    def create(self, data: LeadCreate) -> Lead:
        lead_id = data.lead_id or f"LEAD-{uuid.uuid4().hex[:8].upper()}"
        lead = Lead(
            lead_id=lead_id,
            tenant_id=data.tenant_id,
            company_name=data.company_name,
            industry=data.industry,
            employee_count=data.employee_count,
            requirement=data.requirement,
            budget=data.budget,
            contact_name=data.contact_name,
            contact_role=data.contact_role,
            email=data.email,
            source=data.source,
            status=data.status,
        )
        self.db.add(lead)
        self.db.flush()
        return lead

    def update_status(self, lead: Lead, status: str) -> Lead:
        lead.status = status
        lead.updated_at = datetime.utcnow()
        self.db.flush()
        return lead

    def get_active_run_for_lead(self, lead_id: str) -> Run | None:
        return (
            self.db.query(Run)
            .filter(Run.lead_id == lead_id, Run.state.in_(list(ACTIVE_RUN_STATES)))
            .order_by(Run.created_at.desc())
            .first()
        )

    def get_latest_run_for_lead(self, lead_id: str) -> Run | None:
        return (
            self.db.query(Run)
            .filter(Run.lead_id == lead_id)
            .order_by(Run.created_at.desc())
            .first()
        )


class RunRepository:
    def __init__(self, db: Session):
        self.db = db
        self._counter = 0

    def get_by_run_id(self, run_id: str) -> Run | None:
        return self.db.query(Run).filter(Run.run_id == run_id).first()

    def get_by_event_id(self, event_id: str) -> Run | None:
        return self.db.query(Run).filter(Run.inbound_event_id == event_id).first()

    def list_runs(self, tenant_id: str | None = None) -> list[Run]:
        q = self.db.query(Run)
        if tenant_id:
            q = q.filter(Run.tenant_id == tenant_id)
        return q.order_by(Run.created_at.desc()).all()

    def count_active_runs(self, tenant_id: str) -> int:
        return (
            self.db.query(func.count(Run.id))
            .filter(Run.tenant_id == tenant_id, Run.state.in_(list(ACTIVE_RUN_STATES)))
            .scalar()
            or 0
        )

    def generate_run_id(self) -> str:
        year = datetime.utcnow().year
        prefix = f"RUN-{year}-"
        existing = (
            self.db.query(Run.run_id)
            .filter(Run.run_id.like(f"{prefix}%"))
            .all()
        )
        max_n = 0
        for (run_id,) in existing:
            try:
                suffix = str(run_id).removeprefix(prefix)
                max_n = max(max_n, int(suffix))
            except ValueError:
                continue
        return f"{prefix}{max_n + 1:06d}"

    def create_run(
        self,
        *,
        tenant_id: str,
        source: str,
        trigger_type: str,
        lead_id: str,
        owner: str,
        budget_limit: int,
        correlation_id: str,
        inbound_event_id: str,
        use_case: str = "sales_lead",
        document_ref: str | None = None,
        supplier_id: str | None = None,
        arrival_source: str | None = None,
        budget_turns: int = 20,
        budget_usd_cents: int = 50,
        budget_seconds: int = 120,
    ) -> Run:
        run = Run(
            run_id=self.generate_run_id(),
            tenant_id=tenant_id,
            source=source,
            trigger_type=trigger_type,
            lead_id=lead_id,
            owner=owner,
            budget_limit=budget_limit,
            state=RunState.ADMITTED.value,
            correlation_id=correlation_id,
            inbound_event_id=inbound_event_id,
            use_case=use_case,
            document_ref=document_ref,
            supplier_id=supplier_id,
            arrival_source=arrival_source,
            budget_turns=budget_turns,
            budget_usd_cents=budget_usd_cents,
            budget_seconds=budget_seconds,
            started_at=datetime.utcnow(),
        )
        self.db.add(run)
        self.db.flush()
        return run

    def update_state(self, run: Run, state: str, reason: str = "") -> Run:
        run.state = state
        if reason:
            run.status_reason = reason
        if state in {
            RunState.HANDED_OFF.value,
            RunState.REJECTED.value,
            RunState.FAILED.value,
            RunState.FINDING_READY.value,
        }:
            run.completed_at = datetime.utcnow()
        self.db.flush()
        return run


class EventRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_event_id(self, event_id: str) -> InboundEvent | None:
        return self.db.query(InboundEvent).filter(InboundEvent.event_id == event_id).first()

    def create_inbound(
        self,
        *,
        event_id: str,
        source: str,
        event_type: str,
        tenant_id: str,
        lead_id: str,
        request_id: str,
        payload: dict,
        signature_valid: bool,
    ) -> InboundEvent:
        event = InboundEvent(
            event_id=event_id,
            source=source,
            event_type=event_type,
            tenant_id=tenant_id,
            lead_id=lead_id,
            request_id=request_id,
            payload_json=json.dumps(payload),
            signature_valid=signature_valid,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def list_for_run(self, run_id: str) -> list[RuntimeEvent]:
        return (
            self.db.query(RuntimeEvent)
            .filter(RuntimeEvent.run_id == run_id)
            .order_by(RuntimeEvent.timestamp.asc())
            .all()
        )

    def count_rejections(self) -> int:
        return (
            self.db.query(func.count(RuntimeEvent.id))
            .filter(RuntimeEvent.action == "rejected")
            .scalar()
            or 0
        )


class QueueRepository:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        *,
        run_id: str,
        tenant_id: str,
        lead_id: str,
        source: str,
        payload: dict | None = None,
    ) -> QueueMessage:
        msg = QueueMessage(
            message_id=f"MSG-{uuid.uuid4().hex[:12].upper()}",
            queue_name=settings.queue_name,
            run_id=run_id,
            tenant_id=tenant_id,
            lead_id=lead_id,
            source=source,
            payload_json=json.dumps(payload or {}),
            status=QueueMessageStatus.PENDING.value,
        )
        self.db.add(msg)
        self.db.flush()
        return msg

    def get_by_run_id(self, run_id: str) -> QueueMessage | None:
        return (
            self.db.query(QueueMessage)
            .filter(QueueMessage.run_id == run_id)
            .order_by(QueueMessage.enqueued_at.desc())
            .first()
        )

    def list_messages(self, status: str | None = None) -> list[QueueMessage]:
        q = self.db.query(QueueMessage).filter(QueueMessage.queue_name == settings.queue_name)
        if status:
            q = q.filter(QueueMessage.status == status)
        return q.order_by(QueueMessage.enqueued_at.desc()).all()

    def dequeue_next(self) -> QueueMessage | None:
        msg = (
            self.db.query(QueueMessage)
            .filter(
                QueueMessage.queue_name == settings.queue_name,
                QueueMessage.status == QueueMessageStatus.PENDING.value,
            )
            .order_by(QueueMessage.enqueued_at.asc())
            .first()
        )
        if msg:
            msg.status = QueueMessageStatus.PROCESSING.value
            msg.attempt += 1
            self.db.flush()
        return msg

    def complete(self, msg: QueueMessage) -> None:
        msg.status = QueueMessageStatus.COMPLETED.value
        msg.processed_at = datetime.utcnow()
        self.db.flush()

    def fail(self, msg: QueueMessage, error: str, max_retries: int) -> None:
        msg.error_message = error
        if msg.attempt >= max_retries:
            msg.status = QueueMessageStatus.DEAD_LETTER.value
        else:
            msg.status = QueueMessageStatus.PENDING.value
        self.db.flush()

    def status_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in QueueMessageStatus}
        rows = (
            self.db.query(QueueMessage.status, func.count(QueueMessage.id))
            .filter(QueueMessage.queue_name == settings.queue_name)
            .group_by(QueueMessage.status)
            .all()
        )
        for status, count in rows:
            counts[status] = count
        return counts
