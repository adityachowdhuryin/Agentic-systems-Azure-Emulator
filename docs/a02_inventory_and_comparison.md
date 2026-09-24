# Assignment 02 — Local sandbox inventory & comparison table

## Inventory (what runs locally)

| Piece | Location | Notes |
|---|---|---|
| Band A ingress / admission / run / dispatch | `backend/app/band_a/` | Dual `use_case`: `invoice_review` \| `sales_lead` |
| CASE email + chat doors | `backend/app/ingestion/invoice_case_adapter.py` | Through orchestrator; raw email stored; agent never sees door |
| Invoice admission (SPF/DKIM/DMARC + sender→supplier) | `backend/app/band_a/invoice_admission.py` | Maps remittance email → vendor master |
| Band B while-loop agent | `backend/app/band_b/agent_loop.py` | Hand-rolled `while` on Foundry Responses API |
| Tool registry (exactly 7) | `backend/app/band_b/registry.py` | Unregistered = unreachable |
| Connectors | `backend/app/band_b/connectors.py` | HTTP → `http://127.0.0.1:8090` |
| Policy gate | `backend/app/band_b/policy_gate.py` | Independent module (T7) |
| Credential broker | `backend/app/band_b/broker.py` | Journal-proven intent → short-lived `b1.*` HMAC tokens (T5) |
| Journal + replay | `backend/app/band_b/journal.py` | Replay = 0 model calls |
| Context assembler | `backend/app/band_b/context.py` | Rebuild each turn; last 6 tool results |
| Mock systems | `services/mock_systems/run_mocks.py` | Port **8090**; accepts HMAC + static pack tokens |
| Foundry model | `foundry/.env` | `gpt-5-mini` (gpt-4o-mini deprecated on account) |
| UI | Dashboard mode switch Invoice / Sales Lead | CASE player, finding, journal, replay |
| API | `/api/v1/invoice/*` | cases, chat, finding, journal, replay, policy-block |

## §14 Reachable surface (agent runtime)

Everything the invoice agent process can actually touch if it tried — not only the seven registered tools:

| Reachable | What | Write? |
|---|---|---|
| Foundry Responses API | Model calls via `DefaultAzureCredential` | No (read inference) |
| Mocks `:8090` | Extract / ERP / policy HTTP | No (read-only tools) |
| SQLite `data/band_a.db` | runs, journal_turns, findings, queue, leads, events | Yes (journal / finding / run state) |
| In-process queue consumer | `mock_consumer` for async dispatch | Yes (dequeues) |
| CASE / pack fixtures on disk | `Assignment_02_Pack/06_invoice_review_data/` | No (read via mocks) |
| `foundry/.env` / process env | Endpoint, model name, broker secret | Read at startup |

Risk this build is near zero because tools are read-only; listing the surface is the habit for Build 03.

## Comparison table (Azure AI Foundry / Python SDK)

| §10 piece | Platform gave | We wrote |
|---|---|---|
| Agent loop | Responses API (`client.responses.create`) with tools | Hand-rolled `while` loop, turn budgets, stop conditions |
| Tool registry | Function tool schema on Responses call | Hard allowlist of 7; `assert_registered` |
| Connectors | nothing | HTTP client to local mocks |
| Policy gate | nothing | `policy_gate.py` independent of prompt |
| Credential broker | nothing | DB intent check + short-lived HMAC; mocks verify scope/TTL |
| Journal | nothing | SQLite `journal_turns` + `findings` |
| Replay | nothing | Rebuild narrative from journal; `model_calls=0` |
| Context assembler | nothing | Rebuild messages each turn; truncate trail |
| Limits | nothing | turns / USD cents / wall-clock on run row |
| Finding | nothing | Structured JSON + `policy_choice_reason` + UI |

## Deferred (Phase 5)

Azure ACA / Service Bus / SQL / Blob / Key Vault and live Zoho/Teams invoice bridges — after local green.

## Acceptance

- Unit: `backend/tests/test_band_b_acceptance.py` (T2, T3, T4 stop×3, T5–T8 structural)
- Live harness: `scripts/a02_acceptance.py` (needs API + mocks + Foundry; exercises T1–T10 without hardcoded passes)
