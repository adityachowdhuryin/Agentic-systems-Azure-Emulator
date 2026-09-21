from sqlalchemy.orm import Session

from app.config import settings
from app.repositories.base import QueueRepository


class MessageTransportService:
    """Thin wrapper over queue repository for Band A boundary clarity."""

    def __init__(self, db: Session):
        self.queue = QueueRepository(db)

    def get_status(self, worker_running: bool) -> dict:
        counts = self.queue.status_counts()
        return {
            "queue_name": settings.queue_name,
            "pending": counts.get("PENDING", 0),
            "processing": counts.get("PROCESSING", 0),
            "completed": counts.get("COMPLETED", 0),
            "failed": counts.get("FAILED", 0),
            "dead_letter": counts.get("DEAD_LETTER", 0),
            "worker_running": worker_running,
        }

    def list_messages(self, status: str | None = None):
        return self.queue.list_messages(status)
