"""Scheduler admission failure demos (presenter path)."""


def test_scheduler_demos_catalog(client):
    r = client.get("/api/v1/scheduler/demos")
    assert r.status_code == 200
    ids = {d["id"] for d in r.json()["demos"]}
    assert ids == {
        "invalid-auth",
        "tenant-mismatch",
        "duplicate",
        "active-run",
        "quota-exceeded",
    }


def test_scheduler_demo_invalid_auth(client):
    r = client.post("/api/v1/scheduler/demos/invalid-auth")
    assert r.status_code == 200
    body = r.json()
    assert body["scenario"] == "invalid-auth"
    assert body["rejected"] is True
    assert body["run_created"] is False
    assert body["outcome"] == "rejected"


def test_scheduler_demo_tenant_mismatch(client):
    r = client.post("/api/v1/scheduler/demos/tenant-mismatch")
    assert r.status_code == 200
    body = r.json()
    assert body["rejected"] is True
    assert body["run_created"] is False


def test_scheduler_demo_duplicate(client):
    r = client.post("/api/v1/scheduler/demos/duplicate")
    assert r.status_code == 200
    body = r.json()
    assert body["run_id"]
    assert body["duplicate"] is True or body["outcome"] in ("duplicate", "completed")


def test_scheduler_demo_active_run(client):
    r = client.post("/api/v1/scheduler/demos/active-run")
    assert r.status_code == 200
    body = r.json()
    assert body["rejected"] is True
    assert body["run_id"]
    assert body["code"] == "ACTIVE_RUN_EXISTS" or "active" in body["message"].lower()


def test_scheduler_demo_quota_exceeded(client):
    r = client.post("/api/v1/scheduler/demos/quota-exceeded")
    assert r.status_code == 200
    body = r.json()
    assert body["rejected"] is True
    assert body["run_created"] is False
    assert body["code"] == "BUDGET_EXCEEDED"
    assert "quota" in body["message"].lower() or "budget" in (body.get("reason") or "").lower()


def test_scheduler_demo_unknown(client):
    r = client.post("/api/v1/scheduler/demos/not-a-real-scenario")
    assert r.status_code == 404


def test_scheduler_demos_reset_clears(client):
    client.post("/api/v1/scheduler/demos/duplicate")
    client.post("/api/v1/scheduler/demos/active-run")
    client.post("/api/v1/scheduler/demos/quota-exceeded")
    r = client.post("/api/v1/scheduler/reset")
    assert r.status_code == 200
    leads = client.get("/api/v1/leads").json()
    demo_ids = {l["lead_id"] for l in leads if str(l["lead_id"]).startswith("LEAD-DEMO-")}
    assert not demo_ids
    runs = client.get("/api/v1/runs").json()
    fill = [x for x in runs if str(x["run_id"]).startswith("RUN-FILL-")]
    assert not fill
