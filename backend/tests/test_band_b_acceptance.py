"""Unit tests for Assignment 02 Band B acceptance pieces (T2–T8 without live model)."""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.band_b.broker import mint_credential, scope_for_tool
from app.band_b.context import build_turn_messages
from app.band_b.journal import record_turn, replay_run, save_finding
from app.band_b.policy_gate import check_tool_allowed
from app.band_b.registry import ALLOWED_TOOLS, assert_registered
from app.database import Base, Lead, LeadStatus, Run, RunState, UseCase


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    lead = Lead(
        lead_id="INV-TEST-1",
        tenant_id="company-a",
        company_name="Test Co",
        industry="IT",
        employee_count=10,
        requirement="Invoice",
        budget=0,
        contact_name="AP",
        contact_role="AP",
        email="ap@test.com",
        source="Invoice Email",
        status=LeadStatus.NEW.value,
    )
    session.add(lead)
    session.flush()
    run = Run(
        run_id="RUN-TEST-001",
        tenant_id="company-a",
        source="zoho",
        trigger_type="event",
        lead_id="INV-TEST-1",
        owner="test",
        budget_limit=10,
        state=RunState.ADMITTED.value,
        correlation_id="c1",
        inbound_event_id="e1",
        use_case=UseCase.INVOICE_REVIEW.value,
        document_ref="docs/CASE-01.pdf",
        supplier_id="V-1001",
        budget_turns=3,
        budget_usd_cents=5,
        budget_seconds=2,
    )
    session.add(run)
    session.commit()
    yield session
    session.close()
    engine.dispose()


def test_t2_unregistered_tool_unreachable():
    assert "check_variance" not in ALLOWED_TOOLS
    with pytest.raises(PermissionError):
        assert_registered("check_variance")


def test_t5_broker_requires_intent():
    with pytest.raises(PermissionError):
        mint_credential("extract_invoice", run_id="r1", intent_recorded=False)
    tok = mint_credential("extract_invoice", run_id="r1", intent_recorded=True)
    assert tok == "extract-scoped-token"
    assert scope_for_tool("get_purchase_order") == "erp"


def test_t7_policy_gate_blocks_cross_supplier():
    ok, _ = check_tool_allowed(
        tool_name="get_vendor",
        tool_args={"supplier_id": "V-1001"},
        supplier_id="V-1001",
        run_supplier_id="V-1001",
    )
    assert ok
    blocked, reason = check_tool_allowed(
        tool_name="get_vendor",
        tool_args={"supplier_id": "V-OTHER"},
        supplier_id="V-OTHER",
        run_supplier_id="V-1001",
    )
    assert not blocked
    assert "outside run scope" in reason

    blocked2, reason2 = check_tool_allowed(
        tool_name="get_policy",
        tool_args={"policy_id": "POL-BLOCK-DEMO"},
        supplier_id=None,
        run_supplier_id="V-1001",
    )
    assert not blocked2
    assert "POL-BLOCK-DEMO" in reason2


def test_t3_t8_journal_and_replay(db):
    record_turn(
        db,
        run_id="RUN-TEST-001",
        turn_no=1,
        saw={"document_ref": "docs/CASE-01.pdf"},
        decided="call:extract_invoice",
        tool_name="extract_invoice",
        tool_args={"document_ref": "docs/CASE-01.pdf"},
        tool_result={"invoice_number": "INV-1"},
    )
    save_finding(
        db,
        run_id="RUN-TEST-001",
        verdict="clean",
        checks=[{"what": "3way", "result": "ok"}],
        policy_ids=["POL-1"],
        reasoning="ok",
        uncertainties=[],
        raw_text="ok",
    )
    db.commit()
    replay = replay_run(db, "RUN-TEST-001")
    assert replay["model_calls"] == 0
    assert replay["cost_cents"] == 0
    assert len(replay["turns"]) == 1
    assert replay["finding"]["verdict"] == "clean"


def test_t6_context_rebuild_no_arrival_door():
    msgs = build_turn_messages(
        document_ref="docs/x.pdf",
        supplier_id="V-1",
        prior_turns=[
            {"tool_name": "extract_invoice", "decided": "call", "tool_result": {"a": 1}},
            {"tool_name": "get_purchase_order", "decided": "call", "tool_result": {"b": 2}},
        ],
    )
    blob = json.dumps(msgs)
    assert "arrival_source" not in blob
    assert "docs/x.pdf" in msgs[1]["content"]
    assert "get_purchase_order" in blob


def test_t4_budget_fields_on_run(db):
    run = db.query(Run).filter(Run.run_id == "RUN-TEST-001").one()
    assert run.budget_turns == 3
    assert run.budget_usd_cents == 5
    assert run.budget_seconds == 2
