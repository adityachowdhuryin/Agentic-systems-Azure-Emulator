def test_zoho_mail_webhook(client):
    payload = {
        "from": "Prospect User <prospect@acmecorp.com>",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "Need AI platform demo",
        "body": "We are looking for a sales qualification workflow.",
        "messageId": "mail-test-001",
    }
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "accepted"
    assert data["lead_id"]
    assert data["run_id"]
    assert data["parsed_mail"]["subject"] == "Need AI platform demo"


def test_zoho_mail_webhook_rejects_bad_key(client):
    r = client.post(
        "/api/v1/webhooks/zoho-mail",
        json={"from": "a@b.com", "subject": "x"},
        headers={"X-Mail-Bridge-Key": "wrong"},
    )
    assert r.status_code == 401


def test_inbound_mail_endpoint(client):
    payload = {
        "from": "sender@acme.com",
        "to": "aditya.chowdhury@giantleapsystems.com",
        "subject": "Need demo",
        "body": "Hello, we need a demo please.",
        "messageId": "mail-endpoint-test",
    }
    created = client.post(
        "/api/v1/webhooks/zoho-mail",
        json=payload,
        headers={"X-Mail-Bridge-Key": "local-mail-bridge-key"},
    )
    run_id = created.json()["run_id"]

    r = client.get(f"/api/v1/runs/{run_id}/inbound-mail")
    assert r.status_code == 200
    mail = r.json()
    assert mail["mail_from"] == "sender@acme.com"
    assert mail["mail_subject"] == "Need demo"
    assert "demo please" in mail["mail_body"]
