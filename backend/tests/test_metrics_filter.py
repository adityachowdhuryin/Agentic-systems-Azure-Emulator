def test_metrics_source_filter(client):
    mail = client.post(
        "/api/v1/webhooks/zoho-mail",
        json={
            "from": "a@acme.com",
            "subject": "Mail metric",
            "body": "hello",
            "messageId": "metrics-mail-1",
        },
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert mail.status_code == 200

    teams = client.post(
        "/api/v1/webhooks/teams",
        json={"text": "Teams metric", "from_name": "Rep", "activity_id": "metrics-teams-1"},
        headers={"X-Teams-Bridge-Key": "local-teams-bridge-key"},
    )
    assert teams.status_code == 200

    all_m = client.get("/api/v1/metrics/summary?source_filter=all").json()
    mail_m = client.get("/api/v1/metrics/summary?source_filter=zoho_mail").json()
    teams_m = client.get("/api/v1/metrics/summary?source_filter=teams").json()

    assert all_m["source_filter"] == "all"
    assert mail_m["source_filter"] == "zoho_mail"
    assert teams_m["source_filter"] == "teams"
    assert mail_m["total_leads"] >= 1
    assert teams_m["total_leads"] >= 1
    assert all_m["total_leads"] >= mail_m["total_leads"] + teams_m["total_leads"] - 1
    # seed leads exist in tests but are not Zoho Mail / Teams
    assert mail_m["total_leads"] < all_m["total_leads"]
    assert teams_m["total_leads"] < all_m["total_leads"]
