def test_scheduler_reset_purges_samples_keeps_live(client):
    """Sample-player Teams/Zoho Mail are deleted; live webhook data survives."""
    from app.services import sample_ingress
    from app.services.scheduler_service import stop_scheduler

    stop_scheduler()
    sample_ingress.reset_player_state()

    live_mail = client.post(
        "/api/v1/webhooks/zoho-mail",
        json={
            "from": "prospect@acme.com",
            "to": "monitor@example.com",
            "subject": "Keep live mail",
            "body": "must survive",
            "messageId": "live-mail-reset-001",
        },
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert live_mail.status_code == 200
    live_mail_lead = live_mail.json()["lead_id"]
    live_mail_run = live_mail.json()["run_id"]

    live_teams = client.post(
        "/api/v1/webhooks/teams",
        json={
            "text": "Keep live Teams",
            "from_name": "Live Rep",
            "activity_id": "live-teams-reset-001",
            "channel_id": "sales-channel",
            "conversation_id": "19:live-conversation",
        },
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert live_teams.status_code == 200
    live_teams_lead = live_teams.json()["lead_id"]
    live_teams_run = live_teams.json()["run_id"]

    samples = client.get("/api/v1/scheduler/samples").json()
    teams_id = samples["teams"][0]["id"]
    zoho_id = samples["zoho"][0]["id"]
    ingested = client.post(
        "/api/v1/scheduler/ingest",
        json={"teams_ids": [teams_id], "zoho_ids": [zoho_id]},
    ).json()
    assert ingested["ingested"] == 2
    sample_run_ids = {r["run_id"] for r in ingested["results"] if r.get("run_id")}
    sample_lead_ids = {r["lead_id"] for r in ingested["results"] if r.get("lead_id")}

    # Simulator-style lead (not live external)
    token = client.post(
        "/api/v1/dev/token",
        json={"sub": "zoho-simulator", "tenant_id": "company-a", "role": "zoho-simulator"},
    ).json()["access_token"]
    sim = client.post(
        "/api/v1/simulators/zoho/leads",
        json={
            "tenant_id": "company-a",
            "company_name": "Sim Corp",
            "industry": "Tech",
            "employee_count": 10,
            "requirement": "demo",
            "budget": 1000,
            "contact_name": "Sim",
            "contact_role": "CTO",
            "email": "sim@simcorp.test",
            "source": "Website",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert sim.status_code == 200
    sim_lead = sim.json()["lead_id"]

    r = client.post("/api/v1/scheduler/reset")
    assert r.status_code == 200

    leads = {l["lead_id"]: l for l in client.get("/api/v1/leads").json()}
    runs = {x["run_id"] for x in client.get("/api/v1/runs").json()}

    assert live_mail_lead in leads
    assert live_teams_lead in leads
    assert live_mail_run in runs
    assert live_teams_run in runs

    for lid in sample_lead_ids:
        assert lid not in leads
    for rid in sample_run_ids:
        assert rid not in runs
    assert sim_lead not in leads
    assert "LEAD-10001" not in leads

    after_samples = client.get("/api/v1/scheduler/samples").json()
    assert all(not s["used"] for s in after_samples["teams"])
    assert all(not s["used"] for s in after_samples["zoho"])

    metrics = client.get("/api/v1/metrics/summary").json()
    assert metrics["total_leads"] == len(leads)
