def test_ingestion_logs_requires_bridge_key(client):
    r = client.get("/api/v1/ingestion-logs?source=teams")
    assert r.status_code == 401


def test_ingestion_logs_teams_only(client):
    mail = client.post(
        "/api/v1/webhooks/zoho-mail",
        json={
            "from": "a@acme.com",
            "subject": "Not teams",
            "body": "mail body",
            "messageId": "ingest-log-mail-1",
        },
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert mail.status_code == 200

    teams = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "Horizon Logistics wants a CRM",
            "from_name": "Sales Rep",
            "activity_id": "ingest-log-teams-1",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert teams.status_code == 200
    teams_run = teams.json()["run_id"]

    r = client.get(
        "/api/v1/ingestion-logs?source=teams&limit=25",
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "teams"
    assert data["count"] >= 1
    run_ids = {row["run_id"] for row in data["rows"]}
    assert teams_run in run_ids
    assert mail.json()["run_id"] not in run_ids

    row = next(x for x in data["rows"] if x["run_id"] == teams_run)
    assert row["source"] == "Teams"
    assert "Horizon" in row["topic"]
    assert row["spend"] is None
    assert row["band_a_stage"] in {"Ingress", "Admission", "Run", "Dispatch", "Transport"}
    assert row["phase"] in {"done", "queued", "running", "rejected", "failed"}
    assert row["received_at"]
    assert row["route"] in {"sync", "async", "—"}
