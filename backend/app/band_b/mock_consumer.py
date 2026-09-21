import asyncio
import json
import logging
import random
import threading
import time

from sqlalchemy.orm import Session

from app.config import settings
from app.database import RunState, SessionLocal, UseCase
from app.repositories.base import QueueRepository, RunRepository
from app.security import add_runtime_event

logger = logging.getLogger(__name__)


def _handle_band_b(db: Session, run) -> dict:
    """Route to invoice agent or sales-lead stub based on use_case."""
    if run and getattr(run, "use_case", None) == UseCase.INVOICE_REVIEW.value:
        from app.band_b.agent_loop import run_invoice_agent

        return run_invoice_agent(db, run)
    return {
        "run_id": run.run_id if run else None,
        "qualification_status": "PENDING_AI_QUALIFICATION",
        "message": "Band A successfully handed the lead to Band B.",
    }


class MockQualificationConsumer:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Mock Band B consumer started")

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        logger.info("Mock Band B consumer stopped")

    def _loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            db = SessionLocal()
            try:
                queue = QueueRepository(db)
                runs = RunRepository(db)
                msg = queue.dequeue_next()
                if not msg:
                    db.close()
                    time.sleep(0.5)
                    continue

                run = runs.get_by_run_id(msg.run_id)
                add_runtime_event(
                    db,
                    run_id=msg.run_id,
                    stage="BAND_B",
                    component="mock_consumer",
                    action="message_consumed",
                    status="SUCCESS",
                    message=f"Band B consumed message {msg.message_id}",
                )
                db.commit()

                if run and getattr(run, "use_case", None) == UseCase.INVOICE_REVIEW.value:
                    result = _handle_band_b(db, run)
                    msg.payload_json = json.dumps({"run_id": msg.run_id, "finding": result})
                    queue.complete(msg)
                    db.commit()
                else:
                    time.sleep(random.uniform(1, 3))
                    result = {
                        "run_id": msg.run_id,
                        "lead_id": msg.lead_id,
                        "qualification_status": "PENDING_AI_QUALIFICATION",
                        "message": "Band A successfully handed the lead to Band B.",
                    }
                    msg.payload_json = json.dumps(result)
                    queue.complete(msg)
                    if run:
                        runs.update_state(run, RunState.HANDED_OFF.value, "Handed off to Band B")
                        add_runtime_event(
                            db,
                            run_id=msg.run_id,
                            stage="BAND_B",
                            component="mock_consumer",
                            action="handed_off",
                            status="SUCCESS",
                            message=result["message"],
                        )
                    db.commit()
            except Exception as exc:
                logger.exception("Consumer error: %s", exc)
                db.rollback()
            finally:
                db.close()

    def process_one(self, db: Session) -> bool:
        """Process a single message synchronously (for tests)."""
        queue = QueueRepository(db)
        runs = RunRepository(db)
        msg = queue.dequeue_next()
        if not msg:
            return False
        run = runs.get_by_run_id(msg.run_id)
        add_runtime_event(
            db,
            run_id=msg.run_id,
            stage="BAND_B",
            component="mock_consumer",
            action="message_consumed",
            status="SUCCESS",
            message=f"Band B consumed message {msg.message_id}",
        )
        if run and getattr(run, "use_case", None) == UseCase.INVOICE_REVIEW.value:
            _handle_band_b(db, run)
            queue.complete(msg)
            db.commit()
            return True
        queue.complete(msg)
        if run:
            runs.update_state(run, RunState.HANDED_OFF.value, "Handed off to Band B")
            add_runtime_event(
                db,
                run_id=msg.run_id,
                stage="BAND_B",
                component="mock_consumer",
                action="handed_off",
                status="SUCCESS",
                message="Band A successfully handed the lead to Band B.",
            )
        db.commit()
        return True


mock_consumer = MockQualificationConsumer()
