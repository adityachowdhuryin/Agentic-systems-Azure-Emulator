"""Presenter-friendly admission demos for the Scheduler tab."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.band_b.mock_consumer import mock_consumer
from app.config import settings
from app.correlation import new_correlation_id
from app.database import ACTIVE_RUN_STATES, Lead, Run, RunState
from app.exceptions import BandAError
from app.repositories.base import LeadRepository, RunRepository
from app.schemas import IngressPayload, LeadCreate
from app.security import create_access_token, decode_token, sign_zoho_payload


def _ok(
    scenario: str,
    *,
    outcome: str,
    message: str,
    run_id: str | None = None,
    rejected: bool = False,
    duplicate: bool = False,
    run_created: bool = False,
    extra: dict | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "scenario": scenario,
        "outcome": outcome,
        "message": message,
        "run_id": run_id,
        "rejected": rejected,
        "duplicate": duplicate,
        "run_created": run_created,
    }
    if extra:
        body.update(extra)
    return body


def _ensure_lead(
    db: Session,
    *,
    lead_id: str,
    tenant_id: str,
    company_name: str,
    email: str,
    source: str = "Zoho Mail",
) -> Lead:
    repo = LeadRepository(db)
    existing = repo.get_by_lead_id(lead_id)
    if existing:
        return existing
    return repo.create(
        LeadCreate(
            lead_id=lead_id,
            tenant_id=tenant_id,
            company_name=company_name,
            industry="Unknown",
            employee_count=0,
            requirement="Admission demo lead",
            budget=0,
            contact_name="Demo Contact",
            contact_role="Demo",
            email=email,
            source=source,
        )
    )


def run_invalid_auth(db: Session) -> dict[str, Any]:
    _ensure_lead(
        db,
        lead_id="LEAD-DEMO-AUTH",
        tenant_id="company-a",
        company_name="Demo Auth Co",
        email="auth-demo@demo.example",
    )
    db.commit()
    payload = IngressPayload(
        source="teams",
        event_type="qualify_lead_request",
        event_id=f"demo-invalid-auth-{uuid.uuid4().hex[:8]}",
        tenant_id="company-a",
        lead_id="LEAD-DEMO-AUTH",
        payload={"message": "Qualify lead LEAD-DEMO-AUTH", "demo_origin": "sample_player"},
    )
    try:
        BandAOrchestrator(db).process(
            payload,
            raw_payload=payload.model_dump(),
            token_claims=None,
            correlation_id=new_correlation_id(),
        )
        db.commit()
        return _ok(
            "invalid-auth",
            outcome="unexpected_success",
            message="Expected rejection but request was accepted",
            run_created=True,
        )
    except BandAError as exc:
        db.commit()
        return _ok(
            "invalid-auth",
            outcome="rejected",
            message=f"Rejected — {exc.message}. No run created (authenticate failed).",
            rejected=True,
            run_created=False,
            extra={"reason": exc.message, "code": exc.code},
        )


def run_tenant_mismatch(db: Session) -> dict[str, Any]:
    _ensure_lead(
        db,
        lead_id="LEAD-DEMO-TENANT",
        tenant_id="company-b",
        company_name="Demo Tenant Co",
        email="tenant-demo@demo.example",
        source="Zoho Mail",
    )
    db.commit()
    token, _ = create_access_token("sales-user-01", "company-a", "sales-user")
    claims = decode_token(token)
    payload = IngressPayload(
        source="teams",
        event_type="qualify_lead_request",
        event_id=f"demo-tenant-mismatch-{uuid.uuid4().hex[:8]}",
        tenant_id="company-b",
        lead_id="LEAD-DEMO-TENANT",
        payload={"message": "Qualify lead LEAD-DEMO-TENANT", "demo_origin": "sample_player"},
        requested_by="sales-user-01",
    )
    try:
        BandAOrchestrator(db).process(
            payload,
            raw_payload=payload.model_dump(),
            token_claims=claims,
            correlation_id=new_correlation_id(),
        )
        db.commit()
        return _ok(
            "tenant-mismatch",
            outcome="unexpected_success",
            message="Expected tenant mismatch rejection",
            run_created=True,
        )
    except BandAError as exc:
        db.commit()
        return _ok(
            "tenant-mismatch",
            outcome="rejected",
            message=f"Rejected — token tenant company-a ≠ request tenant company-b.",
            rejected=True,
            run_created=False,
            extra={"reason": exc.message, "code": exc.code},
        )


def run_duplicate(db: Session) -> dict[str, Any]:
    lead = _ensure_lead(
        db,
        lead_id="LEAD-DEMO-DUP",
        tenant_id="company-a",
        company_name="Demo Duplicate Co",
        email="dup-demo@demo.example",
    )
    db.commit()
    token, _ = create_access_token("zoho-simulator", "company-a", "zoho-simulator")
    claims = decode_token(token)
    event_id = "demo-scheduler-duplicate-fixed-id"

    payload = {
        "source": "zoho",
        "event_type": "lead_created",
        "event_id": event_id,
        "tenant_id": "company-a",
        "lead_id": lead.lead_id,
        "payload": {
            "company_name": lead.company_name,
            "demo_origin": "sample_player",
        },
    }
    sig = sign_zoho_payload(payload)
    ingress = IngressPayload(**payload)
    orch = BandAOrchestrator(db)
    r1 = orch.process(
        ingress,
        raw_payload=payload,
        token_claims=claims,
        correlation_id=new_correlation_id(),
        zoho_signature=sig,
    )
    r2 = orch.process(
        ingress,
        raw_payload=payload,
        token_claims=claims,
        correlation_id=new_correlation_id(),
        zoho_signature=sig,
    )
    db.commit()
    run_id = r2.get("run_id") or r1.get("run_id")
    return _ok(
        "duplicate",
        outcome="duplicate" if r2.get("duplicate") else "completed",
        message=(
            f"Same event_id twice → idempotent. First and second both use {run_id} "
            f"(duplicate={bool(r2.get('duplicate'))})."
        ),
        run_id=run_id,
        duplicate=bool(r2.get("duplicate")),
        run_created=not bool(r1.get("duplicate")),
        extra={"first": r1, "second": r2},
    )


def run_active_run(db: Session) -> dict[str, Any]:
    """Create async run left QUEUED, then second request for same lead → ACTIVE_RUN_EXISTS."""
    worker_was_running = mock_consumer.is_running
    if worker_was_running:
        mock_consumer.stop()

    lead = _ensure_lead(
        db,
        lead_id="LEAD-DEMO-ACTIVE",
        tenant_id="company-a",
        company_name="Demo Active Run Co",
        email="active-demo@demo.example",
    )
    # Finish any prior active run on this lead so setup is clean
    for run in (
        db.query(Run)
        .filter(Run.lead_id == lead.lead_id, Run.state.in_(list(ACTIVE_RUN_STATES)))
        .all()
    ):
        run.state = RunState.HANDED_OFF.value
        run.status_reason = "Cleared for admission active-run demo"
    db.commit()

    token, _ = create_access_token("zoho-simulator", "company-a", "zoho-simulator")
    claims = decode_token(token)
    orch = BandAOrchestrator(db)

    first_event = f"demo-active-first-{uuid.uuid4().hex[:8]}"
    first_payload = {
        "source": "zoho",
        "event_type": "lead_created",
        "event_id": first_event,
        "tenant_id": "company-a",
        "lead_id": lead.lead_id,
        "payload": {
            "company_name": lead.company_name,
            "demo_origin": "sample_player",
            "mail_from": lead.email,
            "mail_subject": "Active run setup",
            "mail_body": "setup",
            "mail_message_id": first_event,
        },
    }
    sig1 = sign_zoho_payload(first_payload)
    r1 = orch.process(
        IngressPayload(**first_payload),
        raw_payload=first_payload,
        token_claims=claims,
        correlation_id=new_correlation_id(),
        zoho_signature=sig1,
        force_sync=False,
    )
    db.commit()
    first_run_id = r1.get("run_id")

    second_event = f"demo-active-second-{uuid.uuid4().hex[:8]}"
    second_payload = {
        "source": "zoho",
        "event_type": "lead_created",
        "event_id": second_event,
        "tenant_id": "company-a",
        "lead_id": lead.lead_id,
        "payload": {
            "company_name": lead.company_name,
            "demo_origin": "sample_player",
            "mail_from": lead.email,
            "mail_subject": "Active run conflict",
            "mail_body": "should reject",
            "mail_message_id": second_event,
        },
    }
    sig2 = sign_zoho_payload(second_payload)
    try:
        orch.process(
            IngressPayload(**second_payload),
            raw_payload=second_payload,
            token_claims=claims,
            correlation_id=new_correlation_id(),
            zoho_signature=sig2,
            force_sync=False,
        )
        db.commit()
        return _ok(
            "active-run",
            outcome="unexpected_success",
            message="Expected ACTIVE_RUN_EXISTS but second request succeeded",
            run_id=first_run_id,
            run_created=True,
            extra={"worker_stopped": worker_was_running},
        )
    except BandAError as exc:
        db.commit()
        return _ok(
            "active-run",
            outcome="rejected",
            message=(
                f"Rejected — lead already has active run {exc.existing_run_id or first_run_id}. "
                f"Worker was {'stopped for this demo' if worker_was_running else 'already off'}."
            ),
            run_id=exc.existing_run_id or first_run_id,
            rejected=True,
            run_created=False,
            extra={
                "reason": exc.message,
                "code": exc.code,
                "existing_run_id": exc.existing_run_id or first_run_id,
                "worker_stopped": worker_was_running,
            },
        )


def run_quota_exceeded(db: Session) -> dict[str, Any]:
    """Fill company-b active-run budget on a filler lead, then request a different lead."""
    tenant_id = "company-b"
    quota = settings.tenant_quota(tenant_id)
    fill_lead = _ensure_lead(
        db,
        lead_id="LEAD-DEMO-QUOTA-FILL",
        tenant_id=tenant_id,
        company_name="Demo Quota Fill Co",
        email="quota-fill@demo.example",
    )
    request_lead = _ensure_lead(
        db,
        lead_id="LEAD-DEMO-QUOTA",
        tenant_id=tenant_id,
        company_name="Demo Quota Co",
        email="quota-demo@demo.example",
    )
    # Clear any prior active runs on the request lead so budget (not active-run) is the gate
    for run in (
        db.query(Run)
        .filter(Run.lead_id == request_lead.lead_id, Run.state.in_(list(ACTIVE_RUN_STATES)))
        .all()
    ):
        run.state = RunState.HANDED_OFF.value
        run.status_reason = "Cleared for admission quota demo"
    db.commit()

    active = RunRepository(db).count_active_runs(tenant_id)
    need = max(0, quota - active)
    suffix = uuid.uuid4().hex[:6]
    for i in range(need):
        db.add(
            Run(
                run_id=f"RUN-FILL-{suffix}-{i:04d}",
                tenant_id=tenant_id,
                source="scheduler",
                trigger_type="scheduler_sweep",
                lead_id=fill_lead.lead_id,
                owner="scheduler",
                budget_limit=quota,
                state=RunState.QUEUED.value,
                correlation_id=f"FILL-{suffix}-{i}",
                inbound_event_id=f"fill-{suffix}-{i}",
            )
        )
    db.commit()

    token, _ = create_access_token("zoho-simulator", tenant_id, "zoho-simulator")
    claims = decode_token(token)
    event_id = f"demo-quota-{uuid.uuid4().hex[:8]}"
    payload = IngressPayload(
        source="zoho",
        event_type="lead_created",
        event_id=event_id,
        tenant_id=tenant_id,
        lead_id=request_lead.lead_id,
        payload={"demo_origin": "sample_player", "company_name": request_lead.company_name},
    )
    raw = payload.model_dump()
    sig = sign_zoho_payload(raw)
    try:
        BandAOrchestrator(db).process(
            payload,
            raw_payload=raw,
            token_claims=claims,
            correlation_id=new_correlation_id(),
            zoho_signature=sig,
        )
        db.commit()
        return _ok(
            "quota-exceeded",
            outcome="unexpected_success",
            message="Expected quota rejection",
            run_created=True,
        )
    except BandAError as exc:
        db.commit()
        return _ok(
            "quota-exceeded",
            outcome="rejected",
            message=f"Rejected — tenant {tenant_id} admission budget / quota exceeded ({quota} active runs).",
            rejected=True,
            run_created=False,
            extra={
                "reason": exc.message,
                "code": exc.code,
                "quota": quota,
                "tenant_id": tenant_id,
            },
        )


SCENARIOS = {
    "invalid-auth": run_invalid_auth,
    "tenant-mismatch": run_tenant_mismatch,
    "duplicate": run_duplicate,
    "active-run": run_active_run,
    "quota-exceeded": run_quota_exceeded,
}


def run_scenario(db: Session, scenario: str) -> dict[str, Any]:
    fn = SCENARIOS.get(scenario)
    if not fn:
        return _ok(
            scenario,
            outcome="error",
            message=f"Unknown scenario: {scenario}",
        )
    return fn(db)
