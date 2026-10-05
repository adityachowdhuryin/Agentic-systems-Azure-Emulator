# Azure deploy runbook (ASL Invoice — Ai-Agent)

## Blocker (must clear before Phase 3–4 cloud create)

Subscription providers are **NotRegistered**. RG Contributor cannot register them.

**Anuj (subscription Owner) must run once:**

```bash
chmod +x azure/infra/register-providers.sh
./azure/infra/register-providers.sh
```

Also grant Aditya **User Access Administrator** on RG `Ai-Agent` (for `assign-roles.sh`), then:

```bash
./azure/infra/deploy.sh
./azure/infra/assign-roles.sh
```

Budget `asl-invoice-30` ($30/mo on Ai-Agent) is already created.

## Resources (prefix `asl-invoice-*` in RG `Ai-Agent`, region `eastus2`)

| Resource | Name |
| --- | --- |
| ACR Basic | `aslinvoiceacr` |
| Container Apps Env | `asl-invoice-cae` |
| Apps | `banda`, `bandb`, `mocks` |
| Service Bus Basic | `asl-invoice-sb` + queues `invoice-review`, `sales-lead-qualification` |
| SQL Basic | `asl-invoice-sql` / `asl_invoice` |
| Storage | `asl-invoice*` / container `documents` |
| Key Vault | `asl-invoice-kv*` |
| Budget | `asl-invoice-30` |

Foundry (existing): `anujthakur-3048` / model `gpt-5-mini`.

## Build & push (after foundation)

```bash
az acr login -n aslinvoiceacr
ACR=aslinvoiceacr.azurecr.io
docker build -f backend/Dockerfile -t $ACR/banda:latest .
docker build -f backend/Dockerfile.worker -t $ACR/bandb:latest .
docker build -f services/mock_systems/Dockerfile -t $ACR/mocks:latest .
docker push $ACR/banda:latest && docker push $ACR/bandb:latest && docker push $ACR/mocks:latest
```

Then deploy `azure/infra/apps.bicep` with foundation outputs.

## Live doors (Phase 5) — done on Azure

1. Zoho Deluge → `https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/api/v1/webhooks/zoho-mail` (+ `X-Mail-Bridge-Key`). Paste Script B from `docs/zoho_deluge_live_invoice.md`.
2. Bot `BandASalesBot` → `https://bridge.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/api/messages` (updated).
3. Retire local ngrok + Desktop webhook for cloud demos (`docs/AZURE_LIVE_CUTOVER.md`).

## Local

`ALWAYS_QUEUE=true` (default). Start worker via Queue panel or `python -m app.band_b.worker`.
`AGENT_RUNTIME=maf` on bandb (default in image — `agent-framework-foundry` in `backend/requirements.txt`). Set `AGENT_RUNTIME=responses` locally to force the hand-rolled Foundry Responses path.
