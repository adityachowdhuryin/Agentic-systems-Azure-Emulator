"""Turn journal + model-free replay."""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.database import Finding, JournalTurn


def record_turn(
    db: Session,
    *,
    run_id: str,
    turn_no: int,
    saw: dict,
    decided: str,
    tool_name: str | None = None,
    tool_args: dict | None = None,
    tool_result: dict | None = None,
    blocked_by_policy: bool = False,
    token_cost_cents: int = 0,
) -> JournalTurn:
    row = JournalTurn(
        run_id=run_id,
        turn_no=turn_no,
        saw_json=json.dumps(saw),
        decided=decided,
        tool_name=tool_name,
        tool_args_json=json.dumps(tool_args or {}),
        tool_result_json=json.dumps(tool_result or {}),
        blocked_by_policy=blocked_by_policy,
        token_cost_cents=token_cost_cents,
    )
    db.add(row)
    db.flush()
    return row


def list_turns(db: Session, run_id: str) -> list[JournalTurn]:
    return (
        db.query(JournalTurn)
        .filter(JournalTurn.run_id == run_id)
        .order_by(JournalTurn.turn_no.asc())
        .all()
    )


def save_finding(
    db: Session,
    *,
    run_id: str,
    verdict: str,
    checks: list,
    policy_ids: list,
    reasoning: str,
    uncertainties: list,
    raw_text: str,
    policy_choice_reason: str | None = None,
) -> Finding:
    existing = db.query(Finding).filter(Finding.run_id == run_id).first()
    if existing:
        finding = existing
    else:
        finding = Finding(run_id=run_id)
        db.add(finding)
    finding.verdict = verdict
    finding.checks_json = json.dumps(checks)
    finding.policy_ids_json = json.dumps(policy_ids)
    finding.reasoning = reasoning
    finding.uncertainties_json = json.dumps(uncertainties)
    finding.raw_text = raw_text
    finding.policy_choice_reason = policy_choice_reason or ""
    db.flush()
    return finding


def replay_run(db: Session, run_id: str) -> dict:
    """Rebuild narrative from journal only — no model calls."""
    turns = list_turns(db, run_id)
    finding = db.query(Finding).filter(Finding.run_id == run_id).first()
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
        "finding": None
        if not finding
        else {
            "verdict": finding.verdict,
            "checks": json.loads(finding.checks_json or "[]"),
            "policy_ids": json.loads(finding.policy_ids_json or "[]"),
            "policy_choice_reason": finding.policy_choice_reason or "",
            "reasoning": finding.reasoning,
            "uncertainties": json.loads(finding.uncertainties_json or "[]"),
            "raw_text": finding.raw_text,
        },
        "model_calls": 0,
        "cost_cents": 0,
    }
