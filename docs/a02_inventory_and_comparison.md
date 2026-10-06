# Assignment 02 — Local sandbox inventory & comparison table

## Inventory (what runs locally)

| Piece | Location | Notes |
|---|---|---|
| Band A ingress / admission / run / dispatch | `backend/app/band_a/` | Dual `use_case`: `invoice_review` \| `sales_lead` |
| CASE email + chat doors | `backend/app/ingestion/invoice_case_adapter.py` | Through orchestrator; raw email stored; agent never sees door |
| Live Zoho / Teams doors | same + webhooks / bridge | Stable `event_id` (messageId or content hash); Azure HTTPS cutover |
| Invoice admission (SPF/DKIM/DMARC + sender→supplier) | `backend/app/band_a/invoice_admission.py` | Maps remittance email → vendor master |
| Band B agent loop | `backend/app/band_b/agent_loop.py` | While-loop + budgets; `_invoke_model` → MAF or Responses |
| MAF adapter | `backend/app/band_b/maf_runtime.py` | `FoundryChatClient` one turn; tools executed outside MAF |
| Tool registry (exactly 7) | `backend/app/band_b/registry.py` | Unregistered = unreachable |
| Connectors | `backend/app/band_b/connectors.py` | HTTP → mocks (`:8090` local / ACA `mocks`) |
| Policy gate | `backend/app/band_b/policy_gate.py` | Independent module (T7) |
| Credential broker | `backend/app/band_b/broker.py` | Journal-proven intent → short-lived `b1.*` HMAC tokens (T5) |
| Journal + replay | `backend/app/band_b/journal.py` | Replay = 0 model calls |
| Context assembler | `backend/app/band_b/context.py` | Rebuild each turn; last 6 tool results |
| Mock systems | `services/mock_systems/run_mocks.py` | Port **8090**; accepts HMAC + static pack tokens |
| Foundry model | `foundry/.env` | `gpt-5-mini` via Agent Framework on Azure `bandb` |
| UI | Dashboard mode switch Invoice / Sales Lead | CASE player, finding, journal, replay, run delete |
| API | `/api/v1/invoice/*` | cases, chat, finding, journal, replay, policy-block |

## §14 Reachable surface (agent runtime)

Everything the invoice agent process can actually touch if it tried — not only the seven registered tools:

| Reachable | What | Write? |
|---|---|---|
| Foundry (via Agent Framework / Responses) | Model calls via `DefaultAzureCredential` | No (read inference) |
| Mocks `:8090` / ACA mocks | Extract / ERP / policy HTTP | No (read-only tools) |
| SQLite or Azure SQL | runs, journal_turns, findings, queue, leads, events | Yes (journal / finding / run state) |
| Queue consumer | SQLite `mock_consumer` or Service Bus worker | Yes (dequeues) |
| Blob / local uploads | Live invoice JSON | Yes (Band A write; Band B/mocks read) |
| CASE / pack fixtures on disk | `Assignment_02_Pack/06_invoice_review_data/` | No (read via mocks) |
| `foundry/.env` / process env | Endpoint, model name, broker secret | Read at startup |

Risk this build is near zero because tools are read-only; listing the surface is the habit for Build 03.

## Comparison table (Azure AI Foundry / Agent Framework)

| §10 piece | Platform gave | We wrote |
|---|---|---|
| Agent loop | Foundry + Agent Framework (`FoundryChatClient`) | While-loop + budgets; MAF one turn via `_invoke_model` (Responses fallback) |
| Tool registry | Function tool schema on model call | Hard allowlist of 7; `assert_registered` |
| Connectors | nothing | HTTP client to mocks (local or ACA) |
| Policy gate | nothing | `policy_gate.py` independent of prompt |
| Credential broker | nothing | DB intent check + short-lived HMAC; mocks verify scope/TTL |
| Journal | nothing | `journal_turns` + `findings` (SQLite / Azure SQL) |
| Replay | nothing | Rebuild narrative from journal; `model_calls=0` |
| Context assembler | nothing | Rebuild messages each turn; truncate trail |
| Limits | nothing | turns / USD cents / wall-clock on run row |
| Finding | nothing | Structured JSON + `policy_choice_reason` + UI |
| Live doors | nothing (your ingress) | Zoho Mail + Teams → Band A webhooks |

## Current architecture

| Piece | How it runs today |
|---|---|
| Band A | Ingress · admission · run · dispatch — no AI (FastAPI `banda`) |
| Band B | Invoice worker — Agent Framework → Foundry `gpt-5-mini` + 7 tools |
| Queue | SQLite local · Azure Service Bus `invoice-review` / `sales-lead-qualification` |
| Model path | `AGENT_RUNTIME=maf` → `FoundryChatClient`; `responses` = fallback |
| Mocks | Fake ERP / extract / policy |
| Data | SQLite + uploads local · Azure SQL + Blob on cloud |
| Identity | `az login` local · Managed Identity on Azure |
| Doors | CASE email · chat · live Zoho · live Teams |

## Azure (live)

ACA (`banda` / `bandb` / `mocks` / `bridge`) + Service Bus + SQL + Blob + Key Vault + App Insights. Live Zoho Deluge and Teams bot point at Azure HTTPS (see `docs/AZURE_LIVE_CUTOVER.md`).

## Acceptance

- Unit: `backend/tests/test_band_b_acceptance.py` (T2–T8, MAF routing, redelivery skip, stable event token)
- Live harness: `scripts/a02_acceptance.py` (needs API + mocks + Foundry; exercises T1–T10 without hardcoded passes)
