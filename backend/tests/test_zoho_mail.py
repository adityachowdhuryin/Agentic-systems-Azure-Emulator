def test_zoho_mail_webhook(client, monkeypatch):
    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "exception:not_an_invoice", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    payload = {
        "from": "Prospect User <prospect@acmecorp.com>",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "Need AI platform demo",
        "body": "We are looking for a sales qualification workflow.",
        "messageId": "mail-test-001",
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data.get("use_case") == "invoice_review"
    assert data.get("inbound_kind") == "non_invoice"
    assert data["run_id"]
    assert data["parsed_mail"]["subject"] == "Need AI platform demo"


def test_zoho_mail_webhook_rejects_bad_key(client):
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json={"from": "a@b.com", "subject": "x"},
        headers={"X-Mail-Bridge-Key": "wrong"},
    )
    assert r.status_code == 401


def test_inbound_mail_endpoint(client, monkeypatch):
    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "exception:not_an_invoice", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    payload = {
        "from": "sender@acme.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "Need demo",
        "body": "Hello, we need a demo please.",
        "messageId": "mail-endpoint-test",
    }
    created = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    run_id = created.json()["run_id"]

    r = client.get(f"/api/v1/runs/{run_id}/inbound-mail")
    assert r.status_code == 200
    mail = r.json()
    assert mail["mail_from"] == "sender@acme.com"
    assert mail["mail_subject"] == "Need demo"
    assert "demo please" in mail["mail_body"]


def test_zoho_mail_live_invoice_body_paste(client, monkeypatch):
    import json
    from pathlib import Path

    from app.ingestion.live_invoice_content import uploads_dir

    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "clean", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    invoice = {
        "invoice_number": "INV-06174",
        "supplier_id": "SUP-1001",
        "supplier_name": "Meridian Fasteners Pty Ltd",
        "invoice_date": "2026-08-28",
        "currency": "AUD",
        "po_reference": "PO-2026-4006",
        "lines": [
            {
                "line_no": 1,
                "item_code": "GSKT-60",
                "quantity": 110,
                "unit_price": 1.85,
                "line_total": 203.5,
            }
        ],
        "total_amount": 203.5,
    }
    payload = {
        "from": "me@example.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "Invoice for review",
        "content": json.dumps(invoice),
        "messageId": "mail-live-body-006",
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["use_case"] == "invoice_review"
    assert data["arrival_source"] == "zoho_mail"
    assert data["document_ref"]
    assert (uploads_dir() / f"{data['document_ref']}.json").exists()


def test_zoho_mail_live_invoice_attachment(client, monkeypatch):
    import base64
    import json

    from app.ingestion.live_invoice_content import uploads_dir

    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "clean", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    invoice = {
        "invoice_number": "INV-01417",
        "supplier_id": "SUP-1001",
        "po_reference": "PO-2026-4009",
        "lines": [
            {"line_no": 1, "item_code": "X", "quantity": 1, "unit_price": 1.0, "line_total": 1.0}
        ],
        "total_amount": 1.0,
    }
    raw = json.dumps(invoice).encode()
    payload = {
        "from": "me@example.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "see attach",
        "body": "plain note",
        "messageId": "mail-live-att-009",
        "attachments": [
            {
                "filename": "CASE-09_INV-01417.json",
                "contentType": "application/json",
                "contentBase64": base64.b64encode(raw).decode(),
            }
        ],
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["use_case"] == "invoice_review"
    assert data.get("inbound_kind") != "non_invoice"
    assert data["document_ref"]
    assert (uploads_dir() / f"{data['document_ref']}.json").exists()


def test_attach_only_ignores_plain_body(client, monkeypatch):
    import base64
    from pathlib import Path

    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "clean", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    pack = (
        Path(__file__).resolve().parents[2]
        / "Assignment_02_Pack"
        / "06_invoice_review_data"
        / "inbound"
        / "documents"
        / "CASE-09_INV-01417.json"
    )
    raw = pack.read_bytes()
    payload = {
        "from": "me@example.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "attach only",
        "body": "please review",
        "messageId": "mail-attach-only-009",
        "attachments": [
            {
                "filename": "CASE-09_INV-01417.json",
                "contentType": "application/json",
                "contentBase64": base64.b64encode(raw).decode(),
            }
        ],
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["use_case"] == "invoice_review"
    mail = client.get(f"/api/v1/runs/{data['run_id']}/inbound-mail").json()
    assert mail["attachment_filename"] == "CASE-09_INV-01417.json"
    assert "INV-01417" in mail["invoice_content"]


def test_zoho_mail_case_in_subject_no_longer_maps_local(client, monkeypatch):
    """CASE-XX in subject alone must not load pack fixtures — non_invoice path."""

    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "exception:not_an_invoice", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    payload = {
        "from": "me@example.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "CASE-06 please",
        "body": "No invoice body here",
        "messageId": "mail-case-subject-only",
        "attachments": "[]",
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("use_case") == "invoice_review"
    assert data.get("inbound_kind") == "non_invoice"
    assert data.get("supplier_id") == "SUP-1001"


def test_zoho_mail_live_invoice_inbound_content(client, monkeypatch):
    import json

    def _fake_agent(db, run):
        from app.database import RunState

        run.state = RunState.FINDING_READY.value
        return {"verdict": "clean", "checks": []}

    monkeypatch.setattr("app.band_b.agent_loop.run_invoice_agent", _fake_agent)

    invoice = {
        "invoice_number": "INV-01417",
        "supplier_id": "SUP-1001",
        "po_reference": "PO-2026-4009",
        "lines": [
            {"line_no": 1, "item_code": "X", "quantity": 1, "unit_price": 1.0, "line_total": 1.0}
        ],
        "total_amount": 1.0,
    }
    payload = {
        "from": "me@example.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "CASE-09 body",
        "content": json.dumps(invoice),
        "messageId": "mail-live-inbound-009",
        "attachments": "[]",
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    mail = client.get(f"/api/v1/runs/{run_id}/inbound-mail").json()
    assert mail["invoice_source"] == "body"
    assert "INV-01417" in mail["invoice_content"]
    assert "SUP-1001" in mail["invoice_content"]
