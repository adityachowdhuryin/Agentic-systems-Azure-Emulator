from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_serializer

from app.timeutils import to_utc_iso


class ErrorDetail(BaseModel):
    code: str
    message: str
    run_created: bool = False
    correlation_id: str
    existing_run_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class IngressPayload(BaseModel):
    source: str
    event_type: str
    event_id: str
    tenant_id: str
    lead_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = None


class IngressResponse(BaseModel):
    run_id: str | None = None
    state: str | None = None
    correlation_id: str
    duplicate: bool = False
    rejected: bool = False
    reason: str | None = None


class LeadCreate(BaseModel):
    lead_id: str | None = None
    tenant_id: str = "company-a"
    company_name: str
    industry: str
    employee_count: int = 0
    requirement: str = ""
    budget: int = 0
    contact_name: str
    contact_role: str = ""
    email: str
    source: str = "Website"
    status: str = "NEW"


class LeadResponse(BaseModel):
    id: int
    lead_id: str
    tenant_id: str
    company_name: str
    industry: str
    employee_count: int
    requirement: str
    budget: int
    contact_name: str
    contact_role: str
    email: str
    source: str
    status: str
    created_at: datetime
    updated_at: datetime
    active_run_id: str | None = None
    latest_run_id: str | None = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def serialize_lead_datetimes(self, value: datetime | None) -> str | None:
        return to_utc_iso(value)


class RunResponse(BaseModel):
    id: int
    run_id: str
    tenant_id: str
    source: str
    trigger_type: str
    lead_id: str
    owner: str
    budget_limit: int
    state: str
    status_reason: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    suspend_requested: bool
    resume_token: str | None
    correlation_id: str
    use_case: str = "sales_lead"
    document_ref: str | None = None
    supplier_id: str | None = None
    dispatch_route: str | None = None
    arrival_source: str | None = None
    budget_turns: int = 20
    budget_usd_cents: int = 50
    budget_seconds: int = 120
    budget_turns_used: int = 0
    budget_usd_spent_cents: int = 0

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "started_at", "completed_at")
    def serialize_run_datetimes(self, value: datetime | None) -> str | None:
        return to_utc_iso(value)


class RuntimeEventResponse(BaseModel):
    event_id: str
    run_id: str | None
    timestamp: datetime
    stage: str
    component: str
    action: str
    status: str
    message: str
    metadata_json: str

    model_config = {"from_attributes": True}

    @field_serializer("timestamp")
    def serialize_event_timestamp(self, value: datetime | None) -> str | None:
        return to_utc_iso(value)


class InboundMailResponse(BaseModel):
    run_id: str
    lead_id: str
    source: str
    event_id: str
    mail_from: str
    mail_to: str
    mail_subject: str
    mail_body: str
    mail_message_id: str
    received_at: str | None = None
    attachment_filename: str = ""
    invoice_content: str = ""
    invoice_source: str = ""


class InboundTeamsResponse(BaseModel):
    run_id: str
    lead_id: str
    source: str
    event_id: str
    teams_from: str
    teams_text: str
    teams_channel: str
    conversation_id: str
    activity_id: str
    received_at: str | None = None


class QueueMessageResponse(BaseModel):
    message_id: str
    queue_name: str
    run_id: str
    tenant_id: str
    lead_id: str
    source: str
    status: str
    attempt: int
    enqueued_at: datetime
    processed_at: datetime | None
    error_message: str

    model_config = {"from_attributes": True}

    @field_serializer("enqueued_at", "processed_at")
    def serialize_queue_datetimes(self, value: datetime | None) -> str | None:
        return to_utc_iso(value)


class QueueStatusResponse(BaseModel):
    queue_name: str
    pending: int
    processing: int
    completed: int
    failed: int
    dead_letter: int
    worker_running: bool


class MetricsSummary(BaseModel):
    total_leads: int
    active_runs: int
    queued_messages: int
    completed_handoffs: int
    rejected_requests: int
    failed_runs: int
    source_filter: str = "all"


class IngestionLogRow(BaseModel):
    run_id: str
    lead_id: str
    tenant_id: str
    owner: str
    topic: str
    source: str
    route: str
    band_a_stage: str
    phase: str
    state: str
    spend: float | None = None
    received_at: str | None = None
    note: str


class IngestionLogsResponse(BaseModel):
    source: str
    count: int
    rows: list[IngestionLogRow]


class TokenRequest(BaseModel):
    sub: str
    tenant_id: str
    role: str
    aud: str = "band-a-local"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TeamsRequest(BaseModel):
    tenant_id: str = "company-a"
    requested_by: str = "sales-user-01"
    message: str
    lead_id: str | None = None


class SchedulerStatusResponse(BaseModel):
    enabled: bool
    interval_seconds: int
    batch_teams: int = 1
    batch_zoho: int = 1
    batch_size: int = 1
    next_run_at: datetime | None = None
    seconds_remaining: int | None = None
    remaining_teams: int = 0
    remaining_zoho: int = 0
    used_teams: int = 0
    used_zoho: int = 0
    last_tick_at: datetime | None = None
    last_tick: dict | None = None
    pause_reason: str | None = None
    last_run_at: datetime | None = None
    last_run_count: int = 0

    @field_serializer("next_run_at", "last_tick_at", "last_run_at")
    def serialize_scheduler_datetimes(self, value: datetime | None) -> str | None:
        return to_utc_iso(value)


class DemoSyncRequest(BaseModel):
    lead_id: str
    tenant_id: str = "company-a"
    source: str = "teams"
    requested_by: str = "sales-user-01"
