"""Invoice review agent loop — Foundry model + gated tools (broker / policy / journal).

Model client: routed via _invoke_model() — MAF FoundryChatClient when AGENT_RUNTIME=maf
(agent-framework-foundry installed), else Foundry Responses API. The control loop
(budgets, journal, gate, broker) stays here so Assignment 02 T-criteria remain enforceable.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.band_b.broker import mint_credential
from app.band_b.connectors import MockConnectors
from app.band_b.context import build_turn_messages, redact_inbound_kind
from app.band_b.journal import record_turn, save_finding
from app.band_b.maf_runtime import _call_model_maf, use_maf
from app.band_b.policy_gate import check_tool_allowed
from app.band_b.registry import TOOL_SCHEMAS, assert_registered
from app.config import settings
from app.database import Finding, InboundEvent, JournalTurn, LeadStatus, Run, RunState, UseCase
from app.repositories.base import LeadRepository, RunRepository
from app.security import add_runtime_event

logger = logging.getLogger(__name__)

# Load foundry/.env if present (project endpoint / model override)
_FOUNDRY_ENV = Path(__file__).resolve().parents[3] / "foundry" / ".env"
if _FOUNDRY_ENV.exists():
    load_dotenv(_FOUNDRY_ENV, override=False)


def _inbound_kind_for_run(db: Session, run: Run) -> str | None:
    if not run.inbound_event_id:
        return None
    ev = db.query(InboundEvent).filter(InboundEvent.event_id == run.inbound_event_id).first()
    if not ev or not ev.payload_json:
        return None
    try:
        stored = json.loads(ev.payload_json)
    except json.JSONDecodeError:
        return None
    inner = stored.get("payload") if isinstance(stored.get("payload"), dict) else stored
    if not isinstance(inner, dict):
        return None
    kind = inner.get("inbound_kind")
    return str(kind) if kind else None


def _model_name() -> str:
    return os.getenv("FOUNDRY_MODEL_NAME") or settings.foundry_model_name


def _endpoint() -> str:
    return os.getenv("FOUNDRY_PROJECT_ENDPOINT") or settings.foundry_project_endpoint


def _estimate_cost_cents(input_chars: int, output_chars: int) -> int:
    # Rough gpt-4o-mini-ish estimate: ~4 chars/token; $0.15/1M in, $0.60/1M out
    in_tok = max(1, input_chars // 4)
    out_tok = max(1, output_chars // 4)
    usd = (in_tok / 1_000_000) * 0.15 + (out_tok / 1_000_000) * 0.60
    return max(1, int(round(usd * 100)))


def _parse_final_finding(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
    return {
        "verdict": "exception:unparsed",
        "checks": [],
        "policy_ids": [],
        "policy_choice_reason": "",
        "reasoning": text[:500],
        "uncertainties": ["Model output was not valid JSON"],
        "raw_text": text,
    }


def _invoke_model(messages: list[dict[str, Any]]):
    """Route to MAF (Agent Framework) or hand-rolled Foundry Responses API."""
    if use_maf():
        return _call_model_maf(messages)
    return _call_model(messages)


def _call_model(messages: list[dict[str, Any]]) -> dict:
    from azure.identity import DefaultAzureCredential
    from azure.ai.projects import AIProjectClient

    endpoint = _endpoint()
    model = _model_name()
    response_tools = []
    for t in TOOL_SCHEMAS:
        response_tools.append(
            {
                "type": "function",
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            }
        )

    with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
    ):
        with project_client.get_openai_client() as client:
            # Responses API requires typed input items (type=message), not bare role/content.
            input_items = []
            for m in messages:
                role = m["role"]
                if role == "system":
                    role = "developer"
                content = m.get("content") or ""
                if not str(content).strip():
                    continue
                input_items.append({"type": "message", "role": role, "content": content})
            resp = client.responses.create(
                model=model,
                input=input_items,
                tools=response_tools,
            )
            return resp


def _extract_tool_calls(resp) -> list[dict]:
    calls = []
    for item in getattr(resp, "output", None) or []:
        itype = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        if itype == "function_call":
            name = getattr(item, "name", None) or item.get("name")
            args_raw = getattr(item, "arguments", None) or item.get("arguments") or "{}"
            call_id = getattr(item, "call_id", None) or item.get("call_id")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            calls.append({"name": name, "arguments": args, "call_id": call_id})
    return calls


def _finding_as_dict(row: Finding) -> dict:
    try:
        checks = json.loads(row.checks_json or "[]")
    except json.JSONDecodeError:
        checks = []
    try:
        policy_ids = json.loads(row.policy_ids_json or "[]")
    except json.JSONDecodeError:
        policy_ids = []
    try:
        uncertainties = json.loads(getattr(row, "uncertainties_json", None) or "[]")
    except json.JSONDecodeError:
        uncertainties = []
    return {
        "verdict": row.verdict or "",
        "checks": checks if isinstance(checks, list) else [],
        "policy_ids": policy_ids if isinstance(policy_ids, list) else [],
        "policy_choice_reason": getattr(row, "policy_choice_reason", None) or "",
        "reasoning": getattr(row, "reasoning", None) or "",
        "uncertainties": uncertainties if isinstance(uncertainties, list) else [],
        "raw_text": getattr(row, "raw_text", None) or "",
    }


def run_invoice_agent(db: Session, run: Run) -> dict:
    if run.use_case != UseCase.INVOICE_REVIEW.value:
        raise ValueError("run_invoice_agent only for invoice_review use_case")

    runs = RunRepository(db)
    leads = LeadRepository(db)
    connectors = MockConnectors()
    started = time.time()
    turn_no = 0

    existing_finding = db.query(Finding).filter(Finding.run_id == run.run_id).first()
    journal_count = (
        db.query(JournalTurn).filter(JournalTurn.run_id == run.run_id).count()
    )

    # Idempotent under Service Bus redelivery: never wipe a finished or in-flight review.
    if existing_finding and (
        run.state == RunState.FINDING_READY.value or journal_count > 0
    ):
        add_runtime_event(
            db,
            run_id=run.run_id,
            stage="BAND_B",
            component="invoice_agent",
            action="agent_skipped_redelivery",
            status="SUCCESS",
            message=(
                f"Skip re-start for {run.document_ref}: "
                f"state={run.state} finding=yes journal_turns={journal_count}"
            ),
        )
        db.commit()
        return _finding_as_dict(existing_finding)

    if journal_count > 0 and run.state == RunState.REVIEWING.value:
        # Another worker (or prior delivery) already progressed — do not wipe.
        add_runtime_event(
            db,
            run_id=run.run_id,
            stage="BAND_B",
            component="invoice_agent",
            action="agent_skipped_redelivery",
            status="SUCCESS",
            message=(
                f"Skip re-start for {run.document_ref}: "
                f"in-flight REVIEWING with {journal_count} journal turn(s)"
            ),
        )
        db.commit()
        return {
            "verdict": "exception:in_progress",
            "checks": [],
            "policy_ids": [],
            "reasoning": "Redelivery skipped — review already in progress.",
            "uncertainties": [],
            "raw_text": "Agent already running or partially complete for this run.",
        }

    # Fresh start only when there is no journal yet
    db.query(JournalTurn).filter(JournalTurn.run_id == run.run_id).delete(synchronize_session=False)
    db.query(Finding).filter(Finding.run_id == run.run_id).delete(synchronize_session=False)
    run.budget_turns_used = 0
    run.budget_usd_spent_cents = 0

    runs.update_state(run, RunState.REVIEWING.value, "Invoice agent started")
    add_runtime_event(
        db,
        run_id=run.run_id,
        stage="BAND_B",
        component="invoice_agent",
        action="agent_started",
        status="SUCCESS",
        message=(
            f"Invoice review agent started for {run.document_ref} "
            f"(runtime={'maf' if use_maf() else 'responses'}, "
            f"inbound_kind_steer={'on' if settings.inbound_kind_steer else 'off'})"
        ),
    )
    db.commit()

    prior: list[dict] = []
    final: dict | None = None
    inbound_kind = _inbound_kind_for_run(db, run)
    # Goal steer + extract-field leak only when flag on (default). Off = free-form A/B.
    steer_kind = inbound_kind if settings.inbound_kind_steer else None

    while True:
        elapsed = time.time() - started
        if run.budget_turns_used >= run.budget_turns:
            final = {
                "verdict": "exception:budget_turns",
                "checks": prior,
                "policy_ids": [],
                "reasoning": "Stopped: turn budget exhausted.",
                "uncertainties": ["Incomplete investigation"],
                "raw_text": "Review stopped — turn limit reached.",
            }
            record_turn(
                db,
                run_id=run.run_id,
                turn_no=turn_no + 1,
                saw={"limit": "turns"},
                decided="stop:turn_budget",
            )
            break
        if run.budget_usd_spent_cents >= run.budget_usd_cents:
            final = {
                "verdict": "exception:budget_money",
                "checks": [],
                "policy_ids": [],
                "reasoning": "Stopped: money budget exhausted.",
                "uncertainties": ["Incomplete investigation"],
                "raw_text": "Review stopped — money limit reached.",
            }
            record_turn(
                db,
                run_id=run.run_id,
                turn_no=turn_no + 1,
                saw={"limit": "money"},
                decided="stop:money_budget",
            )
            break
        if elapsed >= run.budget_seconds:
            final = {
                "verdict": "exception:budget_time",
                "checks": [],
                "policy_ids": [],
                "reasoning": "Stopped: wall-clock budget exhausted.",
                "uncertainties": ["Incomplete investigation"],
                "raw_text": "Review stopped — time limit reached.",
            }
            record_turn(
                db,
                run_id=run.run_id,
                turn_no=turn_no + 1,
                saw={"limit": "time"},
                decided="stop:time_budget",
            )
            break

        turn_no += 1
        messages = build_turn_messages(
            document_ref=run.document_ref or "",
            supplier_id=run.supplier_id,
            prior_turns=prior,
            inbound_kind=steer_kind,
        )
        saw = {
            "document_ref": run.document_ref,
            "supplier_id": run.supplier_id,
            "inbound_kind": inbound_kind,
            "inbound_kind_steer": settings.inbound_kind_steer,
            "prior_tool_count": len([p for p in prior if p.get("tool_name")]),
        }

        try:
            resp = _invoke_model(messages)
        except Exception as exc:
            logger.exception("Model call failed")
            final = {
                "verdict": "exception:model_error",
                "checks": [],
                "policy_ids": [],
                "reasoning": str(exc),
                "uncertainties": ["Model call failed"],
                "raw_text": f"Agent error: {exc}",
            }
            record_turn(
                db,
                run_id=run.run_id,
                turn_no=turn_no,
                saw=saw,
                decided=f"model_error:{exc}",
            )
            break

        out_text = getattr(resp, "output_text", None) or ""
        tool_calls = _extract_tool_calls(resp)
        cost = _estimate_cost_cents(len(json.dumps(messages)), len(out_text) + 200)
        run.budget_turns_used += 1
        run.budget_usd_spent_cents += cost

        if not tool_calls:
            final = _parse_final_finding(out_text)
            record_turn(
                db,
                run_id=run.run_id,
                turn_no=turn_no,
                saw=saw,
                decided="final_finding",
                tool_result=final,
                token_cost_cents=cost,
            )
            break

        # Execute all tool calls from this model response (one journal row each)
        executed = 0
        for call in tool_calls:
            tool_name = call["name"]
            tool_args = call["arguments"] or {}
            journal_turn = turn_no + executed

            try:
                assert_registered(tool_name)
            except PermissionError as exc:
                record_turn(
                    db,
                    run_id=run.run_id,
                    turn_no=journal_turn,
                    saw=saw,
                    decided=str(exc),
                    tool_name=tool_name,
                    tool_args=tool_args,
                    blocked_by_policy=True,
                    token_cost_cents=cost,
                )
                prior.append(
                    {
                        "decided": str(exc),
                        "tool_name": tool_name,
                        "tool_result": {"error": "unregistered"},
                    }
                )
                executed += 1
                continue

            allowed, reason = check_tool_allowed(
                tool_name=tool_name,
                tool_args=tool_args,
                supplier_id=tool_args.get("supplier_id"),
                run_supplier_id=run.supplier_id,
            )
            if not allowed:
                record_turn(
                    db,
                    run_id=run.run_id,
                    turn_no=journal_turn,
                    saw=saw,
                    decided=reason,
                    tool_name=tool_name,
                    tool_args=tool_args,
                    blocked_by_policy=True,
                    token_cost_cents=cost,
                )
                prior.append(
                    {
                        "decided": reason,
                        "tool_name": tool_name,
                        "tool_result": {"blocked": True, "reason": reason},
                    }
                )
                db.commit()
                executed += 1
                continue

            # Intent journaled BEFORE minting credential (T5)
            intent_turn = record_turn(
                db,
                run_id=run.run_id,
                turn_no=journal_turn,
                saw=saw,
                decided=f"call:{tool_name}",
                tool_name=tool_name,
                tool_args=tool_args,
                tool_result={"status": "intent_recorded"},
                token_cost_cents=cost,
            )
            db.flush()

            try:
                cred = mint_credential(db, run_id=run.run_id, tool_name=tool_name)
                result = connectors.call(tool_name, tool_args, cred)
            except Exception as exc:
                result = {"error": str(exc)}
                cred = None

            journal_result = result
            if cred and isinstance(result, dict) and "error" not in result:
                journal_result = {
                    **result,
                    "_broker": {"credential_kind": "b1", "token_prefix": cred[:24]},
                }
            intent_turn.tool_result_json = json.dumps(journal_result)
            model_result = result
            if not settings.inbound_kind_steer and isinstance(result, dict):
                model_result = redact_inbound_kind(result)
            prior.append(
                {
                    "decided": f"call:{tool_name}",
                    "tool_name": tool_name,
                    "tool_result": model_result,
                }
            )
            db.commit()
            executed += 1
        if executed > 1:
            turn_no += executed - 1

    if final is None:
        final = {
            "verdict": "exception:incomplete",
            "checks": [],
            "policy_ids": [],
            "reasoning": "Agent ended without a finding.",
            "uncertainties": [],
            "raw_text": "No finding produced.",
        }

    save_finding(
        db,
        run_id=run.run_id,
        verdict=str(final.get("verdict") or ""),
        checks=final.get("checks") or [],
        policy_ids=final.get("policy_ids") or [],
        reasoning=str(final.get("reasoning") or ""),
        uncertainties=final.get("uncertainties") or [],
        raw_text=str(final.get("raw_text") or final.get("reasoning") or ""),
        policy_choice_reason=str(final.get("policy_choice_reason") or ""),
    )
    runs.update_state(run, RunState.FINDING_READY.value, "Finding ready")
    lead = leads.get_by_lead_id(run.lead_id)
    if lead:
        leads.update_status(lead, LeadStatus.QUALIFIED.value)
    add_runtime_event(
        db,
        run_id=run.run_id,
        stage="BAND_B",
        component="invoice_agent",
        action="finding_ready",
        status="SUCCESS",
        message=f"Verdict: {final.get('verdict')}",
    )
    db.commit()
    return final
