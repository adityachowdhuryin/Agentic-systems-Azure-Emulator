#!/usr/bin/env python3
"""
Acceptance harness for ASL-BUILD-02 T1–T10 (local).

Usage (backend venv):
  cd backend && .venv/bin/python ../scripts/a02_acceptance.py

Prerequisites:
  - mock systems on :8090 (HMAC broker secret defaults match backend)
  - API on :8000
  - Azure login for Foundry (FOUNDRY_MODEL_NAME in foundry/.env)

Writes docs/a02_acceptance_results.json with per-test evidence.
Structural T2/T4–T6 also exercised in-process (and T4 via pytest).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
API = "http://127.0.0.1:8000"
OUT = ROOT / "docs" / "a02_acceptance_results.json"

# Ensure backend package imports work when run from scripts/
sys.path.insert(0, str(BACKEND))


def _req(method: str, path: str, body: dict | None = None, timeout: int = 300) -> dict:
    data = None if body is None else json.dumps(body).encode()
    r = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _wait_finding(run_id: str, label: str, results: dict) -> dict | None:
    for _ in range(90):
        try:
            finding = _req("GET", f"/api/v1/invoice/runs/{run_id}/finding")
            results["runs"][f"finding_{label}"] = finding
            return finding
        except urllib.error.HTTPError:
            time.sleep(2)
    return None


def _structural_tests(results: dict) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.band_b.broker import mint_credential
    from app.band_b.context import build_turn_messages
    from app.band_b.journal import record_turn
    from app.band_b.registry import assert_registered
    from app.database import Base, Lead, LeadStatus, Run, RunState, UseCase

    # T2
    try:
        assert_registered("check_variance")
        results["tests"]["T2"] = {"pass": False, "evidence": "check_variance was registered"}
    except PermissionError as exc:
        results["tests"]["T2"] = {"pass": True, "evidence": str(exc)}

    # T6
    msgs = build_turn_messages(
        document_ref="docs/x.pdf",
        supplier_id="V-1",
        prior_turns=[{"tool_name": "extract_invoice", "decided": "call", "tool_result": {"a": 1}}],
    )
    blob = json.dumps(msgs)
    results["tests"]["T6"] = {
        "pass": "arrival_source" not in blob and "docs/x.pdf" in blob,
        "evidence": {"has_arrival_source": "arrival_source" in blob},
    }

    # T5 — temporary sqlite for intent proof
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(
        Lead(
            lead_id="INV-HARNESS",
            tenant_id="company-a",
            company_name="H",
            industry="IT",
            employee_count=1,
            requirement="x",
            budget=0,
            contact_name="A",
            contact_role="AP",
            email="a@t.com",
            source="Invoice Email",
            status=LeadStatus.NEW.value,
        )
    )
    db.add(
        Run(
            run_id="RUN-HARNESS-T5",
            tenant_id="company-a",
            source="zoho",
            trigger_type="event",
            lead_id="INV-HARNESS",
            owner="harness",
            budget_limit=10,
            state=RunState.ADMITTED.value,
            correlation_id="h1",
            inbound_event_id="h1",
            use_case=UseCase.INVOICE_REVIEW.value,
            document_ref="docs/x.pdf",
            supplier_id="V-1",
            budget_turns=5,
            budget_usd_cents=50,
            budget_seconds=60,
        )
    )
    db.commit()

    refused = False
    try:
        mint_credential(db, run_id="RUN-HARNESS-T5", tool_name="extract_invoice")
    except PermissionError:
        refused = True

    record_turn(
        db,
        run_id="RUN-HARNESS-T5",
        turn_no=1,
        saw={},
        decided="call:extract_invoice",
        tool_name="extract_invoice",
        tool_args={},
        tool_result={"status": "intent_recorded"},
    )
    db.commit()
    tok = mint_credential(db, run_id="RUN-HARNESS-T5", tool_name="extract_invoice")
    results["tests"]["T5"] = {
        "pass": refused and tok.startswith("b1.extract."),
        "evidence": {"refused_without_intent": refused, "token_prefix": tok[:40]},
    }
    db.close()
    engine.dispose()

    # T4 — run the three budget-stop unit tests
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_band_b_acceptance.py::test_t4_stop_turn_budget",
            "tests/test_band_b_acceptance.py::test_t4_stop_money_budget",
            "tests/test_band_b_acceptance.py::test_t4_stop_time_budget",
            "-q",
        ],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "PYTHONPATH": "."},
    )
    results["tests"]["T4"] = {
        "pass": proc.returncode == 0,
        "evidence": {
            "pytest_returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-500:],
            "stderr": (proc.stderr or "")[-300:],
        },
    }


def main() -> int:
    results: dict = {"tests": {}, "runs": {}, "notes": []}
    try:
        cases = _req("GET", "/api/v1/invoice/cases")["cases"]
    except Exception as exc:
        print(f"API not reachable: {exc}")
        return 1

    results["case_count"] = len(cases)
    print(f"Found {len(cases)} CASE emails")

    _structural_tests(results)

    # T9: email + chat same agent path (CASE-01)
    email = _req("POST", "/api/v1/invoice/cases/CASE-01/ingest?force_sync=true")
    chat = _req("POST", "/api/v1/invoice/chat/CASE-01")
    results["runs"]["email_CASE-01"] = email
    results["runs"]["chat_CASE-01"] = chat
    results["tests"]["T9"] = {
        "pass": email.get("use_case") == "invoice_review"
        and chat.get("use_case") == "invoice_review"
        and email.get("document_ref") == chat.get("document_ref")
        and email.get("arrival_source") == "case_email"
        and chat.get("arrival_source") == "chat",
        "evidence": {
            "email_run": email.get("run_id"),
            "chat_run": chat.get("run_id"),
            "document_ref": email.get("document_ref"),
            "email_arrival": email.get("arrival_source"),
            "chat_arrival": chat.get("arrival_source"),
        },
    }

    _wait_finding(email["run_id"], "email", results)
    _wait_finding(chat["run_id"], "chat", results)

    # T1: second case for different tool order
    email2 = _req("POST", "/api/v1/invoice/cases/CASE-04/ingest?force_sync=true")
    results["runs"]["email_CASE-04"] = email2
    _wait_finding(email2["run_id"], "CASE-04", results)
    for _ in range(30):
        try:
            j1 = _req("GET", f"/api/v1/invoice/runs/{email['run_id']}/journal")
            j2 = _req("GET", f"/api/v1/invoice/runs/{email2['run_id']}/journal")
            results["runs"]["journal_CASE-01"] = j1
            results["runs"]["journal_CASE-04"] = j2
            order1 = [t.get("tool_name") for t in j1["turns"] if t.get("tool_name")]
            order2 = [t.get("tool_name") for t in j2["turns"] if t.get("tool_name")]
            results["tests"]["T1"] = {
                "pass": order1 != order2 and bool(order1) and bool(order2),
                "evidence": {"order_CASE-01": order1, "order_CASE-04": order2},
            }
            break
        except urllib.error.HTTPError:
            time.sleep(2)
    else:
        results["tests"]["T1"] = {"pass": False, "evidence": "timeout waiting for journals"}

    # T3 journal present
    j = results["runs"].get("journal_CASE-01") or {}
    results["tests"]["T3"] = {
        "pass": bool(j.get("turns")),
        "evidence": {"turn_count": len(j.get("turns") or [])},
    }

    # T8 replay
    replay = _req("GET", f"/api/v1/invoice/runs/{email['run_id']}/replay")
    results["tests"]["T8"] = {
        "pass": replay.get("model_calls") == 0 and replay.get("cost_cents") == 0,
        "evidence": {"model_calls": replay.get("model_calls"), "cost_cents": replay.get("cost_cents")},
    }

    # T7 force policy block on finished run
    try:
        block = _req("POST", f"/api/v1/invoice/runs/{email['run_id']}/demo/policy-block")
        j_after = _req("GET", f"/api/v1/invoice/runs/{email['run_id']}/journal")
        blocked = [t for t in (j_after.get("turns") or []) if t.get("blocked_by_policy")]
        results["tests"]["T7"] = {
            "pass": bool(blocked) and bool(block.get("blocked")),
            "evidence": {
                "blocks_in_journal": len(blocked),
                "demo_reason": block.get("reason"),
            },
        }
    except Exception as exc:
        results["tests"]["T7"] = {"pass": False, "evidence": str(exc)}

    # T10 CASE-05 low confidence → uncertainties
    case05 = _req("POST", "/api/v1/invoice/cases/CASE-05/ingest?force_sync=true")
    results["runs"]["email_CASE-05"] = case05
    finding05 = _wait_finding(case05["run_id"], "CASE-05", results) or {}
    unc = finding05.get("uncertainties") or []
    results["tests"]["T10"] = {
        "pass": bool(unc),
        "evidence": {"uncertainties": unc, "verdict": finding05.get("verdict")},
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str))
    summary = {k: v.get("pass") for k, v in results["tests"].items()}
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT}")
    return 0 if all(summary.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
