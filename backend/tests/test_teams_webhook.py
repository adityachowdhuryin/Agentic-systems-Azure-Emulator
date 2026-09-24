def test_teams_webhook_rejects_bad_key(client):
    r = client.post(
        "/api/v1/webhooks/teams",
        json={"text": "hello"},
        headers={"X-Teams-Bridge-Key": "wrong"},
    )
    assert r.status_code == 401


def test_teams_webhook_qualify_text_is_non_invoice(client):
    """Live Teams without pack JSON → invoice_review non_invoice (not sales_lead)."""
    r = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "Qualify lead LEAD-10001",
            "from_name": "Aditya Chowdhury",
            "from_id": "aad-user-01",
            "channel_id": "Sales Lead Qualification",
            "conversation_id": "conv-1",
            "activity_id": "act-qualify-10001",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data["use_case"] == "invoice_review"
    assert data.get("inbound_kind") == "non_invoice"
    assert data["run_id"]
    assert data["arrival_source"] == "teams"
    assert data["parsed_teams"]["text"] == "Qualify lead LEAD-10001"

    inbound = client.get(f"/api/v1/runs/{data['run_id']}/inbound-teams")
    assert inbound.status_code == 200
    body = inbound.json()
    assert body["teams_from"] == "Aditya Chowdhury"
    assert "LEAD-10001" in body["teams_text"]


def test_teams_webhook_free_text_non_invoice(client):
    r = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "Horizon Logistics wants a 50-user CRM",
            "from_name": "Sales Rep",
            "from_id": "aad-user-02",
            "channel_id": "19:channel-id",
            "conversation_id": "conv-2",
            "activity_id": "act-freetext-001",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data["use_case"] == "invoice_review"
    assert data.get("inbound_kind") == "non_invoice"
    assert data["run_id"]
    assert data["supplier_id"] == "SUP-1001"

    inbound = client.get(f"/api/v1/runs/{data['run_id']}/inbound-teams")
    assert inbound.status_code == 200
    msg = inbound.json()
    assert msg["teams_from"] == "Sales Rep"
    assert "Horizon Logistics" in msg["teams_text"]


def test_teams_webhook_case_tag_alone_is_non_invoice(client):
    """Live Teams no longer maps CASE-XX to pack fixtures."""
    r = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "CASE-06 please review",
            "from_name": "AP Clerk",
            "from_id": "aad-user-03",
            "channel_id": "19:channel-id",
            "conversation_id": "conv-3",
            "activity_id": "act-case-006",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data["use_case"] == "invoice_review"
    assert data.get("inbound_kind") == "non_invoice"
    assert data.get("case_id") is None
    assert data["arrival_source"] == "teams"
    assert str(data.get("document_ref") or "").startswith("live-NONINV")


def test_teams_webhook_json_paste_invoice(client):
    """Prose + pack-shaped JSON in Teams text → live invoice (like Zoho body)."""
    import json

    from app.ingestion.live_invoice_content import uploads_dir

    invoice = {
        "invoice_number": "INV-02254",
        "supplier_id": "SUP-1001",
        "supplier_name": "Meridian Fasteners Pty Ltd",
        "invoice_date": "2026-08-28",
        "currency": "AUD",
        "po_reference": "PO-2026-4002",
        "lines": [
            {
                "line_no": 1,
                "item_code": "BOLT-M8",
                "quantity": 100,
                "unit_price": 0.45,
                "line_total": 45.0,
            }
        ],
        "total_amount": 45.0,
    }
    text = "i have a problem with this bill\n\n" + json.dumps(invoice)
    r = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": text,
            "from_name": "AP Clerk",
            "from_id": "aad-user-04",
            "channel_id": "19:channel-id",
            "conversation_id": "conv-4",
            "activity_id": "act-paste-02254",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "accepted"
    assert data["use_case"] == "invoice_review"
    assert data.get("inbound_kind") != "non_invoice"
    assert data.get("live_invoice") is True
    assert data["supplier_id"] == "SUP-1001"
    assert data["arrival_source"] == "teams"
    assert data["document_ref"]
    assert "INV-02254" in data["document_ref"]
    assert (uploads_dir() / f"{data['document_ref']}.json").exists()
