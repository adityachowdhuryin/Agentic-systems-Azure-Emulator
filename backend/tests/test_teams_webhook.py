def test_teams_webhook_rejects_bad_key(client):
    r = client.post(
        "/api/v1/webhooks/teams",
        json={"text": "hello"},
        headers={"X-Teams-Bridge-Key": "wrong"},
    )
    assert r.status_code == 401


def test_teams_webhook_qualify_existing_lead(client):
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
    assert data["lead_id"] == "LEAD-10001"
    assert data["created_lead"] is False
    assert data["run_id"]
    assert data["state"] == "HANDED_OFF"
    assert data["parsed_teams"]["text"] == "Qualify lead LEAD-10001"

    events = client.get(f"/api/v1/runs/{data['run_id']}/events").json()
    assert any(e["action"] == "sync_selected" for e in events)

    mail = client.get(f"/api/v1/runs/{data['run_id']}/inbound-teams")
    assert mail.status_code == 200
    body = mail.json()
    assert body["teams_from"] == "Aditya Chowdhury"
    assert "LEAD-10001" in body["teams_text"]
    assert body["teams_channel"] == "Sales Lead Qualification"


def test_teams_webhook_free_text_creates_lead(client):
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
    assert data["created_lead"] is True
    assert data["lead_id"].startswith("LEAD-")
    assert data["lead_id"] != "LEAD-10001"
    assert data["run_id"]
    assert data["state"] == "HANDED_OFF"

    events = client.get(f"/api/v1/runs/{data['run_id']}/events").json()
    assert any(e["action"] == "sync_selected" for e in events)

    inbound = client.get(f"/api/v1/runs/{data['run_id']}/inbound-teams")
    assert inbound.status_code == 200
    msg = inbound.json()
    assert msg["teams_from"] == "Sales Rep"
    assert "Horizon Logistics" in msg["teams_text"]
