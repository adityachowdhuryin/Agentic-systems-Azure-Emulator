# Azure Emulator — Local & Azure Architecture

Based on the current codebase (Band A FastAPI, Band B invoice agent via Microsoft Agent Framework or Foundry Responses fallback, mocks, live Zoho/Teams doors).

**Azure (infra):** ACA + SQL + Service Bus + Blob + Key Vault + App Insights — without over-building.

**Band B implementation:** Microsoft Agent Framework (`agent-framework-foundry`) inside the `bandb` worker when `AGENT_RUNTIME=maf`. The outer governance loop (budgets, policy gate, broker, journal) stays in `backend/app/band_b/agent_loop.py`; MAF handles one model turn per iteration via `FoundryChatClient`. Fallback: hand-rolled Foundry Responses API when `AGENT_RUNTIME=responses` or MAF is not installed. Band A stays FastAPI / Azure SDK with **no AI**. Foundry remains the **model** endpoint.

| Metric | Value |
| --- | --- |
| Local processes | 5 |
| Use cases | 2 |
| Band B tools | 7 |
| Cloud dependency today | 1 (Foundry) |

---

## 1. Local architecture

Source of truth: `backend/app`, `services/mock_systems`, `frontend`, external webhook + ngrok.

Band B uses the while-loop in `backend/app/band_b/agent_loop.py` with model calls routed through `_invoke_model()` → MAF (`maf_runtime._call_model_maf`) or Responses API (`_call_model`). Azure `bandb` sets `AGENT_RUNTIME=maf`.

### Process topology

```
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│ External callers    │   │ Tunnel + bridge     │   │ React UI :5173      │
│ Zoho Mail Deluge    │   │ ngrok → :8080       │   │ Invoice | Sales Lead│
│ Azure Bot → Teams   │   │ webhook Express     │   │ Vite /api → :8000   │
│ Dashboard sims      │   │ Zoho / Teams routes │   │ Polling ~1–2s       │
└─────────┬───────────┘   └─────────┬───────────┘   └─────────┬───────────┘
          │                         │                         │
          └─────────────────────────┼─────────────────────────┘
                                    ▼
          ┌──────────────────────────────────────────────────┐
          │  Band A + Band B API · FastAPI · uvicorn :8000   │
          │  Ingress · admission · runs · webhooks · agent   │
          │  SQLite queue + mock_consumer · BackgroundTasks  │
          └───────────────────────┬──────────────────────────┘
                                  │
          ┌───────────────────────┴──────────────────────────┐
          │                                                  │
          ▼                                                  ▼
┌─────────────────────┐                          ┌─────────────────────┐
│ Mock systems :8090  │                          │ Persistence / AI    │
│ extract · ERP ·     │                          │ SQLite band_a.db    │
│ policy · b1.* toks  │                          │ invoice_uploads/    │
└─────────────────────┘                          │ Foundry (cloud)     │
                                                 └─────────────────────┘
```

### Primary data flows (local)

**Invoice doors**

- **CASE email / chat (UI):** API → Band A orchestrator → sync or async → Band B → mocks → finding/journal. Chat always sync; agent is door-blind.
- **Live Zoho:** Deluge → ngrok → bridge → `/webhooks/zoho-mail` → parse attach/body → uploads → Band A → `force_sync=True` → Band B in-process.
- **Live Teams:** Bot → ngrok → bridge → `/webhooks/teams` → JSON paste or non_invoice → Band A async → BackgroundTasks Band B → bot polls finding.

**Sales Lead**

- Dashboard Zoho/Teams/Scheduler simulators → Band A → SQLite queue → mock_consumer (no LLM). Live Zoho/Teams bot text no longer creates sales_lead.

---

## 2. Azure architecture

Same **control-flow** shape as the agreed Band A / Band B split: Band A (no AI) admits work and hands off durably; Band B (AI) is a worker that consumes the run. Replace local processes with managed Azure services.

**Layers inside Band B (do not confuse):**

| Layer | What it is | Azure / package |
| --- | --- | --- |
| Host | Process that pulls the queue and runs the agent | Container Apps (`bandb`) |
| Agent SDK | Tool-calling loop / agent abstractions | **Microsoft Agent Framework** (`agent-framework`) — library **inside** `bandb` |
| Model | LLM inference | Azure AI Foundry (unchanged role) |

Agent Framework does **not** appear as its own box next to SQL / Service Bus / Blob. It replaces the hand-rolled `agent_loop` implementation **inside** the worker.

```
┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│ Callers             │   │ Edge (no ngrok)     │   │ Static Web Apps     │
│ Zoho Deluge HTTPS   │   │ ACA HTTPS ingress   │   │ React build         │
│ Azure Bot → Teams   │   │ Bot → ACA           │   │ API rewrite → Band A│
│ Browser             │   │ APIM later (opt)    │   │ Entra optional      │
└─────────┬───────────┘   └─────────┬───────────┘   └─────────┬───────────┘
          └─────────────────────────┼─────────────────────────┘
                                    ▼
     ┌──────────────┐                    ┌──────────────┐
     │ ACA: banda   │                    │ ACA: mocks   │
     │ Band A API   │                    │ ERP/extract  │
     │ No AI        │                    │ internal only│
     │ webhooks     │                    └──────▲───────┘
     └──────┬───────┘                           │
            │ durable handoff                   │ tools
            ▼                                   │
     ┌──────────────┐   ┌──────────────┐        │
     │ Service Bus  │──▶│ ACA: bandb   │────────┘
     │ invoice-rev. │   │ Invoice wrkr │
     │ (DLQ)        │   │ Agent Frame- │──▶ AI Foundry (model)
     └──────────────┘   │ work + tools │
                        └──────┬───────┘
                               │
            ┌──────────────────┼──────────────────┐
            ▼                  ▼                  ▼
     ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
     │ Azure SQL    │   │ Blob Storage │   │ Key Vault    │
     │ Basic        │   │ documents    │   │ secrets      │
     └──────────────┘   └──────────────┘   └──────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │ App Insights │
                        │ traces/alerts│
                        └──────────────┘
```

**Bridge decision:** Prefer retiring the Node webhook bridge in Azure — point Zoho Deluge and the Bot messaging endpoint straight at Band A HTTPS on ACA. Keep a thin bridge only if Bot Framework adapter code must stay in Node.

---

## 3. Local → Azure mapping

| Local | Role today | Azure service | Why / notes |
| --- | --- | --- | --- |
| frontend :5173 | React dashboard | Static Web Apps | Static SPA; cheap; API proxy to Band A |
| FastAPI :8000 Band A | Ingress, admission, runs, webhooks (**no AI**) | Container Apps (`banda`) | Long-lived HTTP; scales; matches existing Docker; stays Azure SDK / FastAPI |
| Band B hand-rolled `agent_loop` (Foundry Responses) | Invoice AI loop (today) | Container Apps (`bandb`) worker + **Microsoft Agent Framework** | Same host (`bandb`); **replace** hand-rolled loop with Agent Framework + tools; still calls Foundry + mocks; separate scale from HTTP; pulls Service Bus |
| mock_consumer + SQLite queue | Async handoff | Service Bus queue | Durable, DLQ, multi-worker |
| mocks :8090 | ERP / extract / policy | Container Apps (`mocks`) | Lab fixtures; internal only |
| `data/band_a.db` SQLite | System of record | Azure SQL Basic | SQLAlchemy ports cleanly |
| `data/invoice_uploads/` | Live invoice JSON | Blob (`documents`) | Shared by Band A writers and Band B / mocks extract |
| Assignment_02_Pack fixtures | CASE docs / ERP / policies | Image bake or Blob mount | Mount into mocks container |
| `.env` secrets, bridge keys | Config / auth secrets | Key Vault + ACA secrets | No secrets in images; MI for KV |
| Dev JWT + Zoho HMAC | Caller auth | Entra + HMAC in KV | Keep HMAC for Zoho |
| broker `b1.*` tokens | Scoped tool credentials | Same HMAC scheme in KV | Must still work under Agent Framework (middleware / tool wrappers); rotate via KV |
| Foundry (laptop `az login`) | Model | Foundry + managed identity from `bandb` | Model only; Agent Framework is the client/SDK, not a replacement for Foundry |
| ngrok + webhook :8080 | Public tunnel | ACA public ingress (+ Bot Service) | Eliminate ngrok |
| APScheduler sample timer | Demo ingest | Timer in `banda` or Functions | Optional for sales_lead demos |
| `runtime_events` logs | Timeline / ops | App Insights | Keep DB timeline; mirror key events |

---

## 4. Major architecture decisions

1. **Keep topology, swap substrates** — Band A / Band B / mocks remain separate; host as containers, not a Functions-only rewrite.
2. **Service Bus over SQLite queue** — Durable delivery + DLQ; direct analogue of `queue_messages`. Target control flow matches Band A → Service Bus → Band B worker.
3. **SQL Basic, not Cosmos** — Schema is relational; Cosmos would force a model rewrite.
4. **Blob for live documents** — Shared object store for `document_ref` JSON.
5. **Band B uses Microsoft Agent Framework** — Target AI implementation inside `bandb` (library, not a new Azure resource). Band A remains FastAPI / Azure SDK with no model calls. Does **not** add Agent Framework as a separate cloud service.
6. **Foundry stays as the model; identity changes** — Foundry is already cloud and remains the LLM endpoint. `bandb` authenticates with managed identity. Agent Framework talks **to** Foundry; it does not replace Foundry.
7. **Defer APIM / AKS** — ACA ingress is enough for lab HTTPS, Zoho, and Bot.

---

## 5. Assumptions / unknowns / confirmations

| Item | Status | Impact |
| --- | --- | --- |
| Subscription / RG | Deploy into existing **`Ai-Agent`** (eastus2); Foundry already there | All new resources use `asl-invoice-*` names in `Ai-Agent` |
| Foundry model deployment name | Runtime uses `gpt-5-mini`; plan may say `gpt-4o-mini` | Model name must match Foundry deployment (env / Agent Framework client config) |
| Band B → Microsoft Agent Framework | **Implemented** (`AGENT_RUNTIME=maf`, `maf_runtime.py`) | Per-turn MAF + existing governance loop; Responses fallback for dev/tests |
| Always-queue vs local sync paths | Local still uses `force_sync` / in-process Band B for some doors | Azure target prefers Band A → Service Bus → `bandb`; confirm whether sync-in-process remains for chat latency |
| Keep Node bridge vs Deluge→ACA direct | Needs product choice | One fewer container if retired |
| Mocks in Azure vs laptop-only | Plan includes ACA mocks | Needed for graded Azure demo |
| Sales Lead on Azure in Phase 5 | Deferred in docs | May ship invoice-only first; sales path is not Agent Framework today |
| Public exposure of mocks | Must stay private | VNet / internal ingress required |
| Zoho Deluge account/folder IDs | Environment-specific | Update invoke URL to ACA hostname |
| Bot App ID/secret location | Today on bridge machine | Move to Key Vault; update messaging endpoint |
| Monthly cost envelope | Budget `asl-invoice-30` = $30 on RG `Ai-Agent` | Re-check Pricing Calculator before Bicep |
| Subscription provider registration | **Blocked** — Anuj must run `azure/infra/register-providers.sh` | Required before ACA/SQL/ACR/SB/KV create |
| User Access Administrator on Ai-Agent | Needed for `assign-roles.sh` | MI → AcrPull / Blob / SB / KV |

---

*Infra analysis plus Band B implementation target (Agent Framework). No application code or Bicep changed by this document. Related: `docs/AZURE_INVOICE_AGENT_PLAN.md`, `docs/local-to-azure-mapping.md`.*