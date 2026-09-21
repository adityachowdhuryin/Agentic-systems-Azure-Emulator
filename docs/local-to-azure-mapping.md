# Local-to-Azure Mapping

This document explains how local components map to a future Azure deployment. The local emulator preserves architecture and interfaces — it is **not** production-equivalent to Azure services.

| Local Component | Future Azure |
|---|---|
| FastAPI ingress (`POST /api/v1/ingress`) | Azure API Management + Azure Functions |
| Local JWT dev tokens (`/api/v1/dev/token`) | Microsoft Entra ID |
| SQLite database | Azure SQL or Cosmos DB |
| SQLite-backed queue (`sales-lead-qualification`) | Azure Service Bus |
| APScheduler (sample ingress timer) | Azure Logic Apps or Azure Functions timer trigger |
| `.env` secrets + bridge keys | Azure Key Vault |
| Structured application logs + runtime event timeline | Azure Monitor / Application Insights |
| React + Vite frontend | Azure Static Web Apps or App Service |
| Zoho Mail via ngrok + webhook bridge → `POST /api/v1/webhooks/zoho-mail` | Public HTTPS / API Management + Zoho Deluge |
| Teams Bot (Azure Bot Service) via ngrok → `POST /api/v1/webhooks/teams` | Azure Bot webhook (no ngrok) + Bot Framework |
| Zoho / Teams **simulators** + sample player | Load / demo harness only (not production ingress) |
| `DELETE /api/v1/runs/{run_id}` (Leads hover purge) | Emulator ops tooling — map to guarded admin purge or omit in production |

## Migration Notes

1. **Keep the orchestrator boundary** — Band A orchestration logic moves to Azure Functions or container apps unchanged in structure.
2. **Replace SQLite queue** with Service Bus queues; message schema stays the same.
3. **Replace dev JWT** with Entra ID app registrations and managed identities for Zoho/scheduler callers.
4. **Ingress** moves behind API Management for rate limiting, WAF, and routing.
5. **Observability** — map `RuntimeEvent` records to Application Insights custom events.
6. **Live bridges** — retire ngrok; point Zoho Deluge and Azure Bot messaging endpoint at the cloud HTTPS host. Bridge auth keys move to Key Vault.
7. **Manual run delete** — local hard-delete is for demo cleanup; production should use soft-delete, retention policies, or a privileged admin API with audit — not an unauthenticated UI ×.

## Known Limitations

- Local JWT is not secure for production.
- SQLite queue lacks Service Bus features (sessions, topics, geo-replication).
- Single-process mock Band B consumer vs scaled workers.
- Live Zoho Mail / Teams work locally only with the webhook bridge + ngrok (or equivalent tunnel).
- Manual `DELETE /api/v1/runs/{run_id}` has no authz beyond local trust — do not ship as-is.
