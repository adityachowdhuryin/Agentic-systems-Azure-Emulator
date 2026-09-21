def test_teams_sync_lead_exposes_latest_run(client):
    teams = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "Acme wants pricing",
            "from_name": "Rep",
            "activity_id": "latest-run-teams-1",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert teams.status_code == 200
    body = teams.json()
    assert body["state"] == "HANDED_OFF"
    lead_id = body["lead_id"]
    run_id = body["run_id"]

    leads = client.get("/api/v1/leads").json()
    lead = next(x for x in leads if x["lead_id"] == lead_id)
    # Sync completes immediately — not "active", but latest run must still surface
    assert lead["active_run_id"] is None
    assert lead["latest_run_id"] == run_id
    assert lead["status"] == "QUALIFIED"
