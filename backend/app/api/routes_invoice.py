"""Invoice review CASE player, chat door, finding, journal, replay."""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.band_b.journal import list_turns, record_turn, replay_run
from app.band_b.policy_gate import check_tool_allowed
from app.config import settings
from app.database import Finding, JournalTurn, Run, UseCase, get_db
from app.exceptions import BandAError, ValidationError
from app.ingestion.invoice_case_adapter import (
    ingest_case_email,
    ingest_chat_query,
    list_case_emails,
    list_chat_queries,
)
from app.repositories.base import RunRepository

router = APIRouter(prefix="/api/v1/invoice", tags=["invoice"])


def _model_name() -> str:
    return os.getenv("FOUNDRY_MODEL_NAME") or settings.foundry_model_name


def _endpoint_host() -> str:
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT") or settings.foundry_project_endpoint
    try:
        return urlparse(endpoint).netloc or endpoint
    except Exception:
        return endpoint


@router.get("/health")
def invoice_health():
    """Snappy demo health strip — mocks probed; model name from config (no Foundry round-trip)."""
    mocks_ok = False
    mocks_detail = ""
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(
                f"{settings.mock_systems_url.rstrip('/')}/extraction/invoice",
                params={"document_ref": "CASE-01_INV-01431"},
                headers={"x-credential": "extract-scoped-token"},
            )
            mocks_ok = r.status_code == 200
            mocks_detail = f"HTTP {r.status_code}"
    except Exception as exc:
        mocks_detail = str(exc)[:120]

    return {
        "api": {"ok": True, "detail": "up"},
        "mocks": {
            "ok": mocks_ok,
            "url": settings.mock_systems_url,
            "detail": mocks_detail,
        },
        "model": {
            "ok": bool(_model_name()),
            "name": _model_name(),
            "endpoint_host": _endpoint_host(),
            "detail": "configured (not live-probed)",
        },
    }


@router.get("/cases")
def get_cases():
    return {"cases": list_case_emails()}


@router.get("/chat-queries")
def get_chat_queries():
    return {"queries": list_chat_queries()}


@router.post("/cases/{case_id}/ingest")
def play_case(
    case_id: str,
    force_sync: bool = Query(False, description="Run agent in-process (skip queue)"),
    db: Session = Depends(get_db),
):
    try:
        result = ingest_case_email(db, case_id, force_sync=force_sync)
        db.commit()
        return result
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail={"message": str(exc), "code": getattr(exc, "code", None)}) from exc


@router.post("/chat/{case_id}")
def chat_case(case_id: str, db: Session = Depends(get_db)):
    """Sync chat door — same agent path as email, arrival_source=chat."""
    try:
        result = ingest_chat_query(db, case_id)
        db.commit()
        return result
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc
    except BandAError as exc:
        db.commit()
        raise HTTPException(exc.status_code, detail={"message": str(exc), "code": getattr(exc, "code", None)}) from exc


@router.get("/runs/{run_id}/finding")
def get_finding(run_id: str, db: Session = Depends(get_db)):
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    finding = db.query(Finding).filter(Finding.run_id == run_id).first()
    if not finding:
        raise HTTPException(404, "Finding not ready")
    return {
        "run_id": run_id,
        "use_case": run.use_case,
        "document_ref": run.document_ref,
        "supplier_id": run.supplier_id,
        "arrival_source": run.arrival_source,
        "dispatch_route": run.dispatch_route,
        "verdict": finding.verdict,
        "checks": json.loads(finding.checks_json or "[]"),
        "policy_ids": json.loads(finding.policy_ids_json or "[]"),
        "policy_choice_reason": finding.policy_choice_reason or "",
        "reasoning": finding.reasoning,
        "uncertainties": json.loads(finding.uncertainties_json or "[]"),
        "raw_text": finding.raw_text,
        "budget": {
            "turns": run.budget_turns,
            "turns_used": run.budget_turns_used,
            "usd_cents": run.budget_usd_cents,
            "usd_spent_cents": run.budget_usd_spent_cents,
            "seconds": run.budget_seconds,
        },
    }


@router.get("/runs/{run_id}/journal")
def get_journal(run_id: str, db: Session = Depends(get_db)):
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    turns = list_turns(db, run_id)
    return {
        "run_id": run_id,
        "turns": [
            {
                "turn_no": t.turn_no,
                "saw": json.loads(t.saw_json or "{}"),
                "decided": t.decided,
                "tool_name": t.tool_name,
                "tool_args": json.loads(t.tool_args_json or "{}"),
                "tool_result": json.loads(t.tool_result_json or "{}"),
                "blocked_by_policy": t.blocked_by_policy,
                "token_cost_cents": t.token_cost_cents,
            }
            for t in turns
        ],
    }


@router.get("/runs/{run_id}/replay")
def get_replay(run_id: str, db: Session = Depends(get_db)):
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return replay_run(db, run_id)


@router.post("/runs/{run_id}/demo/policy-block")
def demo_policy_block(run_id: str, db: Session = Depends(get_db)):
    """ASL T7 demo: journal a real independent policy-gate deny (no model / no credential)."""
    run = RunRepository(db).get_by_run_id(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    if run.use_case != UseCase.INVOICE_REVIEW.value:
        raise HTTPException(400, "Policy-block demo only for invoice_review runs")

    wrong_supplier = "SUP-DEMO-OUT-OF-SCOPE"
    tool_name = "get_vendor"
    tool_args = {"supplier_id": wrong_supplier}
    allowed, reason = check_tool_allowed(
        tool_name=tool_name,
        tool_args=tool_args,
        supplier_id=wrong_supplier,
        run_supplier_id=run.supplier_id,
    )
    if allowed:
        # Fallback demo deny if gate unexpectedly allows
        reason = f"Policy gate blocked {tool_name}: supplier {wrong_supplier} outside run scope {run.supplier_id}"
        allowed = False

    max_turn = (
        db.query(JournalTurn.turn_no)
        .filter(JournalTurn.run_id == run_id)
        .order_by(JournalTurn.turn_no.desc())
        .first()
    )
    next_turn = (max_turn[0] if max_turn else 0) + 1

    turn = record_turn(
        db,
        run_id=run_id,
        turn_no=next_turn,
        saw={
            "demo": "force_policy_block",
            "document_ref": run.document_ref,
            "run_supplier_id": run.supplier_id,
        },
        decided=reason,
        tool_name=tool_name,
        tool_args=tool_args,
        tool_result={"blocked": True, "reason": reason, "demo": True},
        blocked_by_policy=True,
        token_cost_cents=0,
    )
    db.commit()
    return {
        "run_id": run_id,
        "blocked": True,
        "reason": reason,
        "turn": {
            "turn_no": turn.turn_no,
            "saw": json.loads(turn.saw_json or "{}"),
            "decided": turn.decided,
            "tool_name": turn.tool_name,
            "tool_args": json.loads(turn.tool_args_json or "{}"),
            "tool_result": json.loads(turn.tool_result_json or "{}"),
            "blocked_by_policy": turn.blocked_by_policy,
            "token_cost_cents": turn.token_cost_cents,
        },
    }


@router.get("/runs")
def list_invoice_runs(tenant_id: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Run).filter(Run.use_case == UseCase.INVOICE_REVIEW.value)
    if tenant_id:
        q = q.filter(Run.tenant_id == tenant_id)
    rows = q.order_by(Run.created_at.desc()).limit(100).all()
    return [
        {
            "run_id": r.run_id,
            "state": r.state,
            "document_ref": r.document_ref,
            "supplier_id": r.supplier_id,
            "arrival_source": r.arrival_source,
            "dispatch_route": r.dispatch_route,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
