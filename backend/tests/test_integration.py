from app.database import ACTIVE_RUN_STATES, Run, RunState


def test_zoho_happy_path(client, zoho_token):
    r = client.post(
        "/api/v1/simulators/zoho/leads",
        headers={"Authorization": f"Bearer {zoho_token}"},
        json={
            "tenant_id": "company-a",
            "company_name": "Test Corp",
            "industry": "Tech",
            "employee_count": 100,
            "requirement": "Test",
            "budget": 1000000,
            "contact_name": "Test User",
            "contact_role": "CTO",
            "email": "test@example.com",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"]
    assert data["event_id"]


def test_teams_happy_path(client, teams_token):
    r = client.post(
        "/api/v1/simulators/teams/request",
        headers={"Authorization": f"Bearer {teams_token}"},
        json={
            "tenant_id": "company-a",
            "requested_by": "sales-user-01",
            "message": "Qualify lead LEAD-10001",
            "lead_id": "LEAD-10001",
        },
    )
    assert r.status_code == 200
    assert r.json()["run_id"]


def test_scheduler_happy_path(client, scheduler_token):
    r = client.post(
        "/api/v1/scheduler/run-now",
        headers={"Authorization": f"Bearer {scheduler_token}"},
        params={"tenant_id": "company-a"},
    )
    assert r.status_code == 200
    assert "runs_created" in r.json()


def test_duplicate_event(client, zoho_token):
    r = client.post("/api/v1/demo/admission/duplicate")
    assert r.status_code == 200
    data = r.json()
    assert data["second"]["duplicate"] is True
    assert data["first"]["run_id"] == data["second"]["run_id"]


def test_invalid_auth(client):
    r = client.post("/api/v1/demo/admission/invalid-auth")
    assert r.status_code == 200
    assert r.json()["rejected"] is True


def test_tenant_mismatch(client):
    r = client.post("/api/v1/demo/admission/tenant-mismatch")
    assert r.status_code == 200
    assert r.json()["rejected"] is True


def test_sync_dispatch(client, teams_token):
    r = client.post(
        "/api/v1/dispatch/demo-sync",
        headers={"Authorization": f"Bearer {teams_token}"},
        json={"lead_id": "LEAD-10003", "tenant_id": "company-a"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "HANDED_OFF"


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200


def test_resend_webhook_rejected_when_active_run(client, zoho_token):
    client.post("/api/v1/queue/worker/stop")
    r1 = client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10001",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )
    assert r1.status_code == 200
    first_run_id = r1.json()["run_id"]

    r2 = client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10001",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )
    assert r2.status_code == 409
    detail = r2.json()["detail"]
    assert detail["code"] == "ACTIVE_RUN_EXISTS"
    assert detail["run_created"] is False
    assert detail["existing_run_id"] == first_run_id

    active_count = (
        client.get("/api/v1/runs?tenant_id=company-a")
        .json()
    )
    active_for_lead = [
        x for x in active_count if x["lead_id"] == "LEAD-10001" and x["state"] in ACTIVE_RUN_STATES
    ]
    assert len(active_for_lead) == 1


def test_resend_allowed_after_handed_off(client, zoho_token, db_session):
    client.post("/api/v1/queue/worker/stop")
    r1 = client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10003",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )
    assert r1.status_code == 200
    first_run_id = r1.json()["run_id"]

    run = db_session.query(Run).filter(Run.run_id == first_run_id).one()
    run.state = RunState.HANDED_OFF.value
    db_session.commit()

    r2 = client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10003",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )
    assert r2.status_code == 200
    assert r2.json()["run_id"] != first_run_id


def test_teams_rejected_when_active_run(client, teams_token, zoho_token):
    client.post("/api/v1/queue/worker/stop")
    client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10001",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )
    r = client.post(
        "/api/v1/simulators/teams/request",
        headers={"Authorization": f"Bearer {teams_token}"},
        json={
            "tenant_id": "company-a",
            "requested_by": "sales-user-01",
            "message": "Qualify lead LEAD-10001",
            "lead_id": "LEAD-10001",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "ACTIVE_RUN_EXISTS"


def test_timeline_shows_rejection_on_existing_run(client, zoho_token):
    client.post("/api/v1/queue/worker/stop")
    r1 = client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10004",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )
    first_run_id = r1.json()["run_id"]

    client.post(
        "/api/v1/simulators/zoho/webhook?lead_id=LEAD-10004",
        headers={"Authorization": f"Bearer {zoho_token}"},
    )

    events = client.get(f"/api/v1/runs/{first_run_id}/events").json()
    actions = [e["action"] for e in events]
    assert "active_run_blocked" in actions
    assert "rejected" in actions
