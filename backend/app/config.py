from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///../data/band_a.db"
    jwt_secret: str = "local-dev-jwt-secret-change-in-production"
    jwt_audience: str = "band-a-local"
    jwt_expiry_minutes: int = 1440
    zoho_webhook_secret: str = "local-zoho-hmac-secret"

    tenant_quota_company_a: int = 100
    tenant_quota_company_b: int = 50

    queue_name: str = "sales-lead-qualification"
    queue_max_retries: int = 3

    scheduler_interval_seconds: int = 60
    scheduler_enabled: bool = False

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    mail_bridge_key: str = "local-mail-bridge-key"
    mail_tenant_id: str = "company-a"
    mail_monitor_address: str = "aditya.chowdhury@giantleapsystems.com"

    teams_bridge_key: str = "local-teams-bridge-key"
    teams_tenant_id: str = "company-a"

    # Invoice review (Assignment 02)
    mock_systems_url: str = "http://127.0.0.1:8090"
    foundry_project_endpoint: str = (
        "https://anujthakur-3048-resource.services.ai.azure.com/api/projects/anujthakur-3048"
    )
    # gpt-4o-mini deprecated; use gpt-5-mini (deployed) — override via foundry/.env
    foundry_model_name: str = "gpt-5-mini"
    broker_hmac_secret: str = "local-broker-hmac-secret-change-me"
    invoice_budget_turns: int = 20
    invoice_budget_usd_cents: int = 100  # $1.00 — gpt-5 turns are slower/costlier than mini
    invoice_budget_seconds: int = 300  # wall-clock; gpt-5 tool loops need headroom
    invoice_tenant_id: str = "company-a"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def tenant_quota(self, tenant_id: str) -> int:
        quotas = {
            "company-a": self.tenant_quota_company_a,
            "company-b": self.tenant_quota_company_b,
        }
        return quotas.get(tenant_id, 10)


settings = Settings()
