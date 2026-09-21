from app.security import create_access_token, decode_token, sign_zoho_payload, validate_role_for_source, verify_zoho_signature


def test_create_and_decode_token():
    token, expires = create_access_token("user-1", "company-a", "sales-user")
    assert expires > 0
    claims = decode_token(token)
    assert claims["sub"] == "user-1"
    assert claims["tenant_id"] == "company-a"


def test_role_validation():
    assert validate_role_for_source("zoho-simulator", "zoho")
    assert validate_role_for_source("scheduler", "scheduler")
    assert validate_role_for_source("sales-user", "teams")
    assert not validate_role_for_source("sales-user", "zoho")


def test_zoho_signature():
    payload = {"source": "zoho", "event_id": "test-1"}
    sig = sign_zoho_payload(payload)
    assert verify_zoho_signature(payload, sig)
    assert not verify_zoho_signature(payload, "invalid")
