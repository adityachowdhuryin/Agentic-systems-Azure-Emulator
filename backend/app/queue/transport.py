"""Queue backends: SQLite (local) or Azure Service Bus."""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.repositories.base import QueueRepository

logger = logging.getLogger(__name__)


def queue_name_for_use_case(use_case: str | None) -> str:
    if use_case == "invoice_review":
        return settings.invoice_queue_name
    return settings.queue_name


class QueueTransport:
    def publish(
        self,
        db: Session,
        *,
        run_id: str,
        tenant_id: str,
        lead_id: str,
        source: str,
        use_case: str | None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError


class SqliteQueueTransport(QueueTransport):
    def publish(
        self,
        db: Session,
        *,
        run_id: str,
        tenant_id: str,
        lead_id: str,
        source: str,
        use_case: str | None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        qname = queue_name_for_use_case(use_case)
        body = payload or {
            "run_id": run_id,
            "lead_id": lead_id,
            "tenant_id": tenant_id,
            "source": source,
            "use_case": use_case,
        }
        msg = QueueRepository(db).enqueue(
            run_id=run_id,
            tenant_id=tenant_id,
            lead_id=lead_id,
            source=source,
            payload=body,
            queue_name=qname,
        )
        return msg.message_id


class ServiceBusQueueTransport(QueueTransport):
    def __init__(self):
        from azure.servicebus import ServiceBusClient

        conn = settings.servicebus_connection_string
        ns = settings.servicebus_fully_qualified_namespace
        if conn:
            self._client = ServiceBusClient.from_connection_string(conn)
        elif ns:
            from azure.identity import DefaultAzureCredential

            self._client = ServiceBusClient(ns, credential=DefaultAzureCredential())
        else:
            raise RuntimeError(
                "SERVICEBUS_CONNECTION_STRING or SERVICEBUS_FULLY_QUALIFIED_NAMESPACE required"
            )

    def publish(
        self,
        db: Session,
        *,
        run_id: str,
        tenant_id: str,
        lead_id: str,
        source: str,
        use_case: str | None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        from azure.servicebus import ServiceBusMessage

        qname = queue_name_for_use_case(use_case)
        body = payload or {
            "run_id": run_id,
            "lead_id": lead_id,
            "tenant_id": tenant_id,
            "source": source,
            "use_case": use_case,
        }
        try:
            SqliteQueueTransport().publish(
                db,
                run_id=run_id,
                tenant_id=tenant_id,
                lead_id=lead_id,
                source=source,
                use_case=use_case,
                payload=body,
            )
        except Exception:
            logger.exception("SQLite mirror enqueue failed (non-fatal)")

        with self._client.get_queue_sender(qname) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(body), message_id=run_id))
        return run_id


def get_queue_transport() -> QueueTransport:
    backend = (settings.queue_backend or "sqlite").lower()
    if backend in {"servicebus", "sb", "azure"}:
        return ServiceBusQueueTransport()
    return SqliteQueueTransport()
