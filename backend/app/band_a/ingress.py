import json
from typing import Any

from sqlalchemy.orm import Session

from app.exceptions import SignatureError, ValidationError
from app.repositories.base import EventRepository
from app.schemas import IngressPayload
from app.security import add_runtime_event, verify_zoho_signature


TRIGGER_TYPE_MAP = {
    "lead_created": "zoho_webhook",
    "qualify_lead_request": "teams_manual",
    "scheduled_qualification": "scheduler_sweep",
}


class IngressService:
    def __init__(self, db: Session):
        self.db = db
        self.events = EventRepository(db)

    def process(
        self,
        payload: IngressPayload,
        *,
        raw_payload: dict[str, Any],
        zoho_signature: str | None = None,
        correlation_id: str,
    ) -> tuple[Any, dict[str, Any]]:
        add_runtime_event(
            self.db,
            stage="INGRESS",
            component="ingress_edge",
            action="request_received",
            status="SUCCESS",
            message=f"Request from {payload.source}",
            metadata={"correlation_id": correlation_id},
        )

        if payload.source not in {"zoho", "teams", "scheduler"}:
            raise ValidationError(f"Unsupported source: {payload.source}")

        if payload.event_type not in TRIGGER_TYPE_MAP:
            raise ValidationError(f"Unsupported event_type: {payload.event_type}")

        existing_inbound = self.events.get_by_event_id(payload.event_id)
        if existing_inbound:
            add_runtime_event(
                self.db,
                stage="INGRESS",
                component="ingress_edge",
                action="request_received",
                status="SUCCESS",
                message=f"Duplicate arrival for event {payload.event_id}",
                metadata={"correlation_id": correlation_id},
            )
            normalized = {
                "source": payload.source,
                "event_type": payload.event_type,
                "event_id": payload.event_id,
                "tenant_id": payload.tenant_id,
                "lead_id": payload.lead_id,
                "payload": payload.payload,
                "requested_by": payload.requested_by,
                "trigger_type": TRIGGER_TYPE_MAP[payload.event_type],
                "inbound_event_id": existing_inbound.event_id,
            }
            return existing_inbound, normalized

        signature_valid = True
        if payload.source == "zoho":
            signature_valid = verify_zoho_signature(raw_payload, zoho_signature)
            if not signature_valid:
                add_runtime_event(
                    self.db,
                    stage="INGRESS",
                    component="ingress_edge",
                    action="verify_signature",
                    status="FAILED",
                    message="Invalid Zoho webhook signature",
                    metadata={"correlation_id": correlation_id},
                )
                raise SignatureError()

        inbound = self.events.create_inbound(
            event_id=payload.event_id,
            source=payload.source,
            event_type=payload.event_type,
            tenant_id=payload.tenant_id,
            lead_id=payload.lead_id,
            request_id=correlation_id,
            payload=raw_payload,
            signature_valid=signature_valid,
        )

        add_runtime_event(
            self.db,
            stage="INGRESS",
            component="ingress_edge",
            action="raw_payload_stored",
            status="SUCCESS",
            message=f"Inbound event {inbound.event_id} stored",
            metadata={"correlation_id": correlation_id},
        )

        normalized = {
            "source": payload.source,
            "event_type": payload.event_type,
            "event_id": payload.event_id,
            "tenant_id": payload.tenant_id,
            "lead_id": payload.lead_id,
            "payload": payload.payload,
            "requested_by": payload.requested_by,
            "trigger_type": TRIGGER_TYPE_MAP[payload.event_type],
            "inbound_event_id": inbound.event_id,
        }

        add_runtime_event(
            self.db,
            stage="INGRESS",
            component="ingress_edge",
            action="acknowledged",
            status="SUCCESS",
            message="Ingress normalization complete",
            metadata={"correlation_id": correlation_id},
        )

        return inbound, normalized
