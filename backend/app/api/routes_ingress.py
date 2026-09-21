import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.band_a.orchestrator import BandAOrchestrator
from app.correlation import get_correlation_id, new_correlation_id
from app.database import get_db
from app.exceptions import BandAError
from app.error_utils import error_response_from_exception
from app.schemas import IngressPayload, IngressResponse
from app.security import decode_token

router = APIRouter(prefix="/api/v1", tags=["ingress"])


def get_bearer_token(authorization: Annotated[str | None, Header()] = None) -> dict | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    try:
        return decode_token(token)
    except ValueError:
        return None


@router.post("/ingress", response_model=IngressResponse)
async def ingress(
    request: Request,
    payload: IngressPayload,
    db: Session = Depends(get_db),
    token_claims: dict | None = Depends(get_bearer_token),
    x_zoho_signature: Annotated[str | None, Header()] = None,
):
    correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
    raw_payload = payload.model_dump()
    force_sync = request.headers.get("X-Force-Sync", "").lower() == "true"

    try:
        orchestrator = BandAOrchestrator(db)
        result = orchestrator.process(
            payload,
            raw_payload=raw_payload,
            token_claims=token_claims,
            correlation_id=correlation_id,
            zoho_signature=x_zoho_signature,
            force_sync=force_sync,
        )
        return IngressResponse(**result)
    except BandAError as exc:
        db.commit()
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=exc.status_code,
            content=error_response_from_exception(exc, correlation_id),
        )
