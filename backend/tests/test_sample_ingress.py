def setup_function():
    from app.services import sample_ingress
    from app.services.scheduler_service import stop_scheduler

    stop_scheduler()
    sample_ingress.reset_player_state()


from app.services import sample_ingress  # noqa: E402


def test_list_samples(client):
    r = client.get("/api/v1/scheduler/samples")
    assert r.status_code == 200
    data = r.json()
    assert len(data["teams"]) >= 8
    assert len(data["zoho"]) >= 8
    assert data["teams"][0]["id"]
    assert data["teams"][0]["title"]


def test_ingest_teams_and_zoho(client):
    samples = client.get("/api/v1/scheduler/samples").json()
    teams_id = samples["teams"][0]["id"]
    zoho_id = samples["zoho"][0]["id"]

    r = client.post(
        "/api/v1/scheduler/ingest",
        json={"teams_ids": [teams_id], "zoho_ids": [zoho_id]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] == 2
    assert all("run_id" in x for x in body["results"] if "error" not in x)

    runs = client.get("/api/v1/runs").json()
    run_ids = {x["run_id"] for x in body["results"] if x.get("run_id")}
    assert run_ids
    matched = [x for x in runs if x["run_id"] in run_ids]
    sources = {x["source"] for x in matched}
    assert "teams" in sources
    assert "zoho" in sources

    # Timeline events exist for created runs
    for run_id in run_ids:
        events = client.get(f"/api/v1/runs/{run_id}/events").json()
        assert len(events) >= 1


def test_timer_independent_batches_and_exhaust(client):
    samples = client.get("/api/v1/scheduler/samples").json()
    teams_to_use = [s["id"] for s in samples["teams"][:-1]]
    client.post("/api/v1/scheduler/ingest", json={"teams_ids": teams_to_use, "zoho_ids": []})

    # Need 2 Teams but only 1 left
    status = client.post(
        "/api/v1/scheduler/timer/start",
        json={"interval_seconds": 30, "batch_teams": 2, "batch_zoho": 0},
    ).json()
    assert status["enabled"] is False
    assert status["pause_reason"] == "samples_exhausted"

    sample_ingress.reset_player_state()
    ok = client.post(
        "/api/v1/scheduler/timer/start",
        json={"interval_seconds": 60, "batch_teams": 1, "batch_zoho": 0},
    ).json()
    assert ok["enabled"] is True
    assert ok["batch_teams"] == 1
    assert ok["batch_zoho"] == 0

    paused = client.post("/api/v1/scheduler/timer/pause").json()
    assert paused["enabled"] is False


def test_scheduler_reset_clears_used(client):
    samples = client.get("/api/v1/scheduler/samples").json()
    teams_id = samples["teams"][0]["id"]
    client.post("/api/v1/scheduler/ingest", json={"teams_ids": [teams_id], "zoho_ids": []})

    before = client.get("/api/v1/scheduler/samples").json()
    assert any(s["id"] == teams_id and s["used"] for s in before["teams"])

    r = client.post("/api/v1/scheduler/reset")
    assert r.status_code == 200
    after = client.get("/api/v1/scheduler/samples").json()
    assert all(not s["used"] for s in after["teams"])
    assert all(not s["used"] for s in after["zoho"])
