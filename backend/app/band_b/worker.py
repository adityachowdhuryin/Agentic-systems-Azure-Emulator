"""Band B worker entrypoint — drains SQLite queue and/or Azure Service Bus."""
from __future__ import annotations

import json
import logging
import os
import sys
import time

# Allow `python -m app.band_b.worker` from backend/
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("band_b.worker")


def _process_run_id(run_id: str) -> None:
    from app.band_b.mock_consumer import _handle_band_b
    from app.database import SessionLocal
    from app.repositories.base import QueueRepository, RunRepository
    from app.security import add_runtime_event
    from app.database import RunState, UseCase

    db = SessionLocal()
    try:
        runs = RunRepository(db)
        queue = QueueRepository(db)
        run = runs.get_by_run_id(run_id)
        if not run:
            logger.error("run %s not found", run_id)
            return
        msg = queue.get_by_run_id(run_id)
        add_runtime_event(
            db,
            run_id=run_id,
            stage="BAND_B",
            component="worker",
            action="message_consumed",
            status="SUCCESS",
            message=f"Worker consumed run {run_id}",
        )
        db.commit()
        result = _handle_band_b(db, run)
        if msg:
            msg.payload_json = json.dumps({"run_id": run_id, "result": result})
            queue.complete(msg)
        if run.use_case != UseCase.INVOICE_REVIEW.value:
            runs.update_state(run, RunState.HANDED_OFF.value, "Handed off to Band B")
        db.commit()
    except Exception:
        logger.exception("Worker failed for %s", run_id)
        db.rollback()
    finally:
        db.close()


def _loop_sqlite() -> None:
    from app.band_b.mock_consumer import mock_consumer

    logger.info("Starting SQLite queue consumer (mock_consumer)")
    mock_consumer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        mock_consumer.stop()


def _loop_servicebus() -> None:
    from azure.servicebus import ServiceBusClient

    from app.config import settings

    conn = settings.servicebus_connection_string
    ns = settings.servicebus_fully_qualified_namespace
    if conn:
        client = ServiceBusClient.from_connection_string(conn)
    elif ns:
        from azure.identity import DefaultAzureCredential

        client = ServiceBusClient(ns, credential=DefaultAzureCredential())
    else:
        raise SystemExit("SERVICEBUS_CONNECTION_STRING or SERVICEBUS_FULLY_QUALIFIED_NAMESPACE required")
    queues = [settings.invoice_queue_name, settings.queue_name]
    logger.info("Starting Service Bus consumer queues=%s", queues)
    # Round-robin receive from both queues
    while True:
        for qname in queues:
            with client.get_queue_receiver(qname, max_wait_time=5) as receiver:
                for msg in receiver:
                    try:
                        body = json.loads(str(msg))
                        run_id = body.get("run_id")
                        if run_id:
                            _process_run_id(run_id)
                        receiver.complete_message(msg)
                    except Exception:
                        logger.exception("SB message failed")
                        receiver.abandon_message(msg)


def main() -> None:
    from app.config import settings
    from app.database import init_db

    init_db()
    backend = (settings.queue_backend or os.getenv("QUEUE_BACKEND") or "sqlite").lower()
    if backend in {"servicebus", "sb", "azure"}:
        _loop_servicebus()
    else:
        _loop_sqlite()


if __name__ == "__main__":
    main()
    sys.exit(0)
