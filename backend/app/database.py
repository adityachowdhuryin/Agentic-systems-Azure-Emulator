from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class LeadStatus(str, Enum):
    NEW = "NEW"
    PENDING_QUALIFICATION = "PENDING_QUALIFICATION"
    QUALIFICATION_IN_PROGRESS = "QUALIFICATION_IN_PROGRESS"
    QUALIFIED = "QUALIFIED"
    REJECTED = "REJECTED"


class RunState(str, Enum):
    RECEIVED = "RECEIVED"
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    DISPATCHED = "DISPATCHED"
    QUEUED = "QUEUED"
    HANDED_OFF = "HANDED_OFF"
    REVIEWING = "REVIEWING"
    FINDING_READY = "FINDING_READY"
    SUSPENDED = "SUSPENDED"
    FAILED = "FAILED"


class UseCase(str, Enum):
    SALES_LEAD = "sales_lead"
    INVOICE_REVIEW = "invoice_review"


ACTIVE_RUN_STATES = {
    RunState.RECEIVED.value,
    RunState.ADMITTED.value,
    RunState.DISPATCHED.value,
    RunState.QUEUED.value,
    RunState.SUSPENDED.value,
    RunState.REVIEWING.value,
}


class QueueMessageStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    company_name: Mapped[str] = mapped_column(String(256))
    industry: Mapped[str] = mapped_column(String(128))
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    requirement: Mapped[str] = mapped_column(Text, default="")
    budget: Mapped[int] = mapped_column(Integer, default=0)
    contact_name: Mapped[str] = mapped_column(String(256))
    contact_role: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(256))
    source: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64), default=LeadStatus.NEW.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    runs: Mapped[list["Run"]] = relationship(back_populates="lead")


class InboundEvent(Base):
    __tablename__ = "inbound_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    lead_id: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(128))
    payload_json: Mapped[str] = mapped_column(Text)
    signature_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64))
    trigger_type: Mapped[str] = mapped_column(String(64))
    lead_id: Mapped[str] = mapped_column(String(64), ForeignKey("leads.lead_id"), index=True)
    owner: Mapped[str] = mapped_column(String(128))
    budget_limit: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[str] = mapped_column(String(64), default=RunState.RECEIVED.value, index=True)
    status_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    suspend_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    resume_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    inbound_event_id: Mapped[str] = mapped_column(String(128), index=True)
    use_case: Mapped[str] = mapped_column(String(64), default=UseCase.SALES_LEAD.value, index=True)
    document_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
    supplier_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    dispatch_route: Mapped[str | None] = mapped_column(String(32), nullable=True)
    arrival_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    budget_turns: Mapped[int] = mapped_column(Integer, default=20)
    budget_usd_cents: Mapped[int] = mapped_column(Integer, default=50)
    budget_seconds: Mapped[int] = mapped_column(Integer, default=120)
    budget_turns_used: Mapped[int] = mapped_column(Integer, default=0)
    budget_usd_spent_cents: Mapped[int] = mapped_column(Integer, default=0)

    lead: Mapped["Lead"] = relationship(back_populates="runs")
    events: Mapped[list["RuntimeEvent"]] = relationship(back_populates="run")
    queue_messages: Mapped[list["QueueMessage"]] = relationship(back_populates="run")
    journal_turns: Mapped[list["JournalTurn"]] = relationship(back_populates="run")
    finding: Mapped["Finding | None"] = relationship(back_populates="run", uselist=False)


class RuntimeEvent(Base):
    __tablename__ = "runtime_events"
    __table_args__ = (Index("ix_runtime_events_run_ts", "run_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runs.run_id"), nullable=True, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    stage: Mapped[str] = mapped_column(String(64))
    component: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")

    run: Mapped["Run | None"] = relationship(back_populates="events")


class QueueMessage(Base):
    __tablename__ = "queue_messages"
    __table_args__ = (Index("ix_queue_status", "queue_name", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    queue_name: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(64))
    lead_id: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(64), default=QueueMessageStatus.PENDING.value)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="")

    run: Mapped["Run"] = relationship(back_populates="queue_messages")


class JournalTurn(Base):
    __tablename__ = "journal_turns"
    __table_args__ = (Index("ix_journal_run_turn", "run_id", "turn_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), index=True)
    turn_no: Mapped[int] = mapped_column(Integer)
    saw_json: Mapped[str] = mapped_column(Text, default="{}")
    decided: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_args_json: Mapped[str] = mapped_column(Text, default="{}")
    tool_result_json: Mapped[str] = mapped_column(Text, default="{}")
    blocked_by_policy: Mapped[bool] = mapped_column(Boolean, default=False)
    token_cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped["Run"] = relationship(back_populates="journal_turns")


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("runs.run_id"), unique=True, index=True)
    verdict: Mapped[str] = mapped_column(String(128), default="")
    checks_json: Mapped[str] = mapped_column(Text, default="[]")
    policy_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    uncertainties_json: Mapped[str] = mapped_column(Text, default="[]")
    raw_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    run: Mapped["Run"] = relationship(back_populates="finding")


engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _sqlite_enable_foreign_keys(dbapi_connection, connection_record):
    if settings.database_url.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_add_column(table: str, column: str, coltype: str) -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows}
        if column not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            conn.commit()


def migrate_schema() -> None:
    """Add new columns to existing SQLite DBs (create_all won't alter)."""
    _sqlite_add_column("runs", "use_case", "VARCHAR(64) DEFAULT 'sales_lead'")
    _sqlite_add_column("runs", "document_ref", "VARCHAR(256)")
    _sqlite_add_column("runs", "supplier_id", "VARCHAR(64)")
    _sqlite_add_column("runs", "dispatch_route", "VARCHAR(32)")
    _sqlite_add_column("runs", "arrival_source", "VARCHAR(64)")
    _sqlite_add_column("runs", "budget_turns", "INTEGER DEFAULT 20")
    _sqlite_add_column("runs", "budget_usd_cents", "INTEGER DEFAULT 50")
    _sqlite_add_column("runs", "budget_seconds", "INTEGER DEFAULT 120")
    _sqlite_add_column("runs", "budget_turns_used", "INTEGER DEFAULT 0")
    _sqlite_add_column("runs", "budget_usd_spent_cents", "INTEGER DEFAULT 0")
    # Orphans appear when SQLite ran without foreign_keys and run_ids were recycled
    if settings.database_url.startswith("sqlite"):
        with engine.connect() as conn:
            conn.exec_driver_sql(
                "DELETE FROM journal_turns WHERE run_id NOT IN (SELECT run_id FROM runs)"
            )
            conn.exec_driver_sql(
                "DELETE FROM findings WHERE run_id NOT IN (SELECT run_id FROM runs)"
            )
            conn.commit()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    migrate_schema()
