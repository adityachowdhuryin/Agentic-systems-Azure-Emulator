from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.correlation import new_correlation_id
from app.database import get_db
from app.error_utils import band_a_error_detail
from app.exceptions import BandAError, ValidationError
from app.ingestion.teams_adapter import TeamsAdapter
from app.ingestion.zoho_adapter import ZohoAdapter
from app.schemas import DemoSyncRequest, LeadCreate, LeadResponse, TeamsRequest, TokenRequest, TokenResponse
from app.security import create_access_token, decode_token, sign_zoho_payload

router = APIRouter(prefix="/api/v1", tags=["simulators"])


def get_bearer_token(authorization: Annotated[str | None, Header()] = None) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        return decode_token(authorization[7:])
    except ValueError:
        return None


@router.post("/dev/token", response_model=TokenResponse)
def dev_token(req: TokenRequest):
    token, expires_in = create_access_token(req.sub, req.tenant_id, req.role, req.aud)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/simulators/zoho/leads")
def zoho_create_lead(
    data: LeadCreate,
    db: Session = Depends(get_db),
    token_claims: dict | None = Depends(get_bearer_token),
):
    if not token_claims:
        token, _ = create_access_token("zoho-simulator", data.tenant_id, "zoho-simulator")
        token_claims = decode_token(token)

    adapter = ZohoAdapter(db)
    cid = new_correlation_id()
    try:
        result = adapter.create_lead_and_webhook(data, token_claims=token_claims, correlation_id=cid)
        return {
            "lead_id": result["lead"].lead_id,
            "event_id": result["event_id"],
            "signature": result["signature"],
            "run_id": result.get("run_id"),
            "state": result.get("state"),
            "correlation_id": cid,
        }
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail=band_a_error_detail(exc)) from exc


@router.post("/simulators/zoho/webhook")
def zoho_webhook(
    lead_id: str,
    db: Session = Depends(get_db),
    token_claims: dict | None = Depends(get_bearer_token),
):
    if not token_claims:
        token, _ = create_access_token("zoho-simulator", "company-a", "zoho-simulator")
        token_claims = decode_token(token)

    adapter = ZohoAdapter(db)
    cid = new_correlation_id()
    try:
        return adapter.send_webhook_for_lead(lead_id, token_claims=token_claims, correlation_id=cid)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail=band_a_error_detail(exc)) from exc


@router.post("/simulators/teams/request")
def teams_request(
    req: TeamsRequest,
    db: Session = Depends(get_db),
    token_claims: dict | None = Depends(get_bearer_token),
    force_sync: bool = False,
):
    if not token_claims:
        token, _ = create_access_token(req.requested_by, req.tenant_id, "sales-user")
        token_claims = decode_token(token)

    adapter = TeamsAdapter(db)
    cid = new_correlation_id()
    try:
        return adapter.process_request(
            message=req.message,
            tenant_id=req.tenant_id,
            requested_by=req.requested_by,
            lead_id=req.lead_id,
            token_claims=token_claims,
            correlation_id=cid,
            force_sync=force_sync,
        )
    except ValidationError as exc:
        raise HTTPException(422, detail={"code": exc.code, "message": exc.message}) from exc
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail=band_a_error_detail(exc)) from exc


@router.post("/dispatch/demo-sync")
def demo_sync_dispatch(
    req: DemoSyncRequest,
    db: Session = Depends(get_db),
    token_claims: dict | None = Depends(get_bearer_token),
):
    if not token_claims:
        token, _ = create_access_token(req.requested_by, req.tenant_id, "sales-user")
        token_claims = decode_token(token)

    adapter = TeamsAdapter(db)
    cid = new_correlation_id()
    message = f"Qualify lead {req.lead_id}"
    return adapter.process_request(
        message=message,
        tenant_id=req.tenant_id,
        requested_by=req.requested_by,
        lead_id=req.lead_id,
        token_claims=token_claims,
        correlation_id=cid,
        force_sync=True,
    )


@router.post("/demo/admission/invalid-auth")
def demo_invalid_auth(db: Session = Depends(get_db)):
    from app.schemas import IngressPayload

    payload = IngressPayload(
        source="teams",
        event_type="qualify_lead_request",
        event_id="demo-invalid-auth",
        tenant_id="company-a",
        lead_id="LEAD-10001",
        payload={"message": "test"},
    )
    orchestrator = BandAOrchestrator(db)
    try:
        orchestrator.process(
            payload,
            raw_payload=payload.model_dump(),
            token_claims=None,
            correlation_id=new_correlation_id(),
        )
    except BandAError as exc:
        db.commit()
        return {"rejected": True, "reason": exc.message, "run_created": False}
    return {"rejected": False}


@router.post("/demo/admission/tenant-mismatch")
def demo_tenant_mismatch(db: Session = Depends(get_db)):
    from app.schemas import IngressPayload

    token, _ = create_access_token("sales-user-01", "company-a", "sales-user")
    claims = decode_token(token)
    payload = IngressPayload(
        source="teams",
        event_type="qualify_lead_request",
        event_id=f"demo-tenant-mismatch-{new_correlation_id()}",
        tenant_id="company-b",
        lead_id="LEAD-10007",
        payload={"message": "Qualify lead LEAD-10007"},
        requested_by="sales-user-01",
    )
    orchestrator = BandAOrchestrator(db)
    try:
        orchestrator.process(
            payload,
            raw_payload=payload.model_dump(),
            token_claims=claims,
            correlation_id=new_correlation_id(),
        )
    except BandAError as exc:
        db.commit()
        return {"rejected": True, "reason": exc.message, "run_created": False}
    return {"rejected": False}


@router.post("/demo/admission/duplicate")
def demo_duplicate(db: Session = Depends(get_db)):
    token, _ = create_access_token("zoho-simulator", "company-a", "zoho-simulator")
    claims = decode_token(token)
    adapter = ZohoAdapter(db)
    cid = new_correlation_id()
    event_id = "demo-duplicate-fixed-id"
    from app.schemas import IngressPayload
    from app.security import sign_zoho_payload

    payload = {
        "source": "zoho",
        "event_type": "lead_created",
        "event_id": event_id,
        "tenant_id": "company-a",
        "lead_id": "LEAD-10001",
        "payload": {"company_name": "ABC Technologies"},
    }
    sig = sign_zoho_payload(payload)
    ingress = IngressPayload(**payload)
    orchestrator = BandAOrchestrator(db)
    r1 = orchestrator.process(ingress, raw_payload=payload, token_claims=claims, correlation_id=cid, zoho_signature=sig)
    r2 = orchestrator.process(ingress, raw_payload=payload, token_claims=claims, correlation_id=cid, zoho_signature=sig)
    return {"first": r1, "second": r2, "duplicate": r2.get("duplicate", False)}


@router.post("/demo/admission/quota-exceeded")
def demo_quota_exceeded(db: Session = Depends(get_db)):
    from app.config import settings
    from app.database import Run, RunState

    token, _ = create_access_token("zoho-simulator", "company-b", "zoho-simulator")
    claims = decode_token(token)

    # Fill quota for company-b (50)
    existing = db.query(Run).filter(Run.tenant_id == "company-b").count()
    quota = settings.tenant_quota("company-b")
    for i in range(max(0, quota - existing)):
        db.add(
            Run(
                run_id=f"RUN-FILL-{i:04d}",
                tenant_id="company-b",
                source="scheduler",
                trigger_type="scheduler_sweep",
                lead_id="LEAD-10007",
                owner="scheduler",
                budget_limit=quota,
                state=RunState.QUEUED.value,
                correlation_id=f"FILL-{i}",
                inbound_event_id=f"fill-{i}",
            )
        )
    db.commit()

    from app.schemas import IngressPayload

    payload = IngressPayload(
        source="zoho",
        event_type="lead_created",
        event_id=f"demo-quota-{new_correlation_id()}",
        tenant_id="company-b",
        lead_id="LEAD-10008",
        payload={},
    )
    from app.security import sign_zoho_payload

    raw = payload.model_dump()
    sig = sign_zoho_payload(raw)
    orchestrator = BandAOrchestrator(db)
    try:
        orchestrator.process(raw_payload=raw, payload=payload, token_claims=claims, correlation_id=new_correlation_id(), zoho_signature=sig)
    except BandAError as exc:
        db.commit()
        return {"rejected": True, "reason": exc.message, "run_created": False}
    return {"rejected": False}
