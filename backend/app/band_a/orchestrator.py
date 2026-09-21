import json
from datetime import datetime

from sqlalchemy.orm import Session

from app.band_a.admission_control import AdmissionControlService
from app.band_a.dispatcher import DispatcherService
from app.band_a.ingress import IngressService
from app.band_a.run_manager import RunManagerService
from app.database import InboundEvent, RuntimeEvent
from app.schemas import IngressPayload


def _attach_events_to_run(db: Session, correlation_id: str, run_id: str) -> None:
    """Link INGRESS/ADMISSION timeline events created before run_id existed."""
    orphans = (
        db.query(RuntimeEvent)
        .filter(RuntimeEvent.run_id.is_(None), RuntimeEvent.stage.in_(["INGRESS", "ADMISSION"]))
        .all()
    )
    for event in orphans:
        meta = json.loads(event.metadata_json or "{}")
        if meta.get("correlation_id") == correlation_id:
            event.run_id = run_id


class BandAOrchestrator:
    """Single entry point for all Band A processing."""

    def __init__(self, db: Session):
        self.db = db
        self.ingress = IngressService(db)
        self.admission = AdmissionControlService(db)
        self.run_manager = RunManagerService(db)
        self.dispatcher = DispatcherService(db)

    def process(
        self,
        payload: IngressPayload,
        *,
        raw_payload: dict,
        token_claims: dict | None,
        correlation_id: str,
        zoho_signature: str | None = None,
        force_sync: bool = False,
    ) -> dict:
        inbound, normalized = self.ingress.process(
            payload,
            raw_payload=raw_payload,
            zoho_signature=zoho_signature,
            correlation_id=correlation_id,
        )

        existing_run_id, is_duplicate = self.admission.process(
            normalized,
            token_claims=token_claims,
            correlation_id=correlation_id,
        )

        if is_duplicate and existing_run_id:
            run = self.run_manager.runs.get_by_run_id(existing_run_id)
            inbound.acknowledged_at = datetime.utcnow()
            self.db.commit()
            return {
                "run_id": existing_run_id,
                "state": run.state if run else "UNKNOWN",
                "correlation_id": correlation_id,
                "duplicate": True,
                "rejected": False,
            }

        run = self.run_manager.create_run(
            normalized,
            token_claims=token_claims or {},
            correlation_id=correlation_id,
        )
        _attach_events_to_run(self.db, correlation_id, run.run_id)

        if force_sync:
            self.dispatcher.dispatch_sync(run)
        else:
            self.dispatcher.dispatch_async(run)

        inbound.acknowledged_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(run)

        return {
            "run_id": run.run_id,
            "state": run.state,
            "correlation_id": correlation_id,
            "duplicate": False,
            "rejected": False,
        }
