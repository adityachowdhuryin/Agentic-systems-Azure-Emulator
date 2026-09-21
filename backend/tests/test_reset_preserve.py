def test_reset_preserves_external_inbound(client):
    """Reset keeps Zoho Mail / Teams leads+runs; clears stub / simulator seed leads."""
    mail = client.post(
        "/api/v1/webhooks/zoho-mail",
        json={
            "from": "prospect@acme.com",
            "to": "monitor@example.com",
            "subject": "Keep me",
            "body": "External mail must survive reset",
            "messageId": "preserve-mail-001",
        },
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert mail.status_code == 200
    mail_lead = mail.json()["lead_id"]
    mail_run = mail.json()["run_id"]

    teams = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "Keep this Teams message",
            "from_name": "Sales Rep",
            "activity_id": "preserve-teams-001",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert teams.status_code == 200
    teams_lead = teams.json()["lead_id"]
    teams_run = teams.json()["run_id"]

    leads_before = {l["lead_id"]: l for l in client.get("/api/v1/leads").json()}
    assert "LEAD-10001" in leads_before  # seeded for tests
    assert leads_before[mail_lead]["source"] == "Zoho Mail"
    assert leads_before[teams_lead]["source"] == "Teams"

    r = client.post("/api/v1/demo/reset")
    assert r.status_code == 200
    assert "preserved" in r.json()["message"].lower() or "Zoho Mail" in r.json()["message"]

    leads_after = {l["lead_id"]: l for l in client.get("/api/v1/leads").json()}
    assert mail_lead in leads_after
    assert teams_lead in leads_after
    assert "LEAD-10001" not in leads_after

    runs_after = {x["run_id"] for x in client.get("/api/v1/runs").json()}
    assert mail_run in runs_after
    assert teams_run in runs_after

    assert client.get(f"/api/v1/runs/{mail_run}/inbound-mail").status_code == 200
    assert client.get(f"/api/v1/runs/{teams_run}/inbound-teams").status_code == 200
