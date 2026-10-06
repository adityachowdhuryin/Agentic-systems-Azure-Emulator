# Azure deploy status (live)

## Working now

| Resource | Name / URL |
| --- | --- |
| RG | `Ai-Agent` |
| ACR Basic | `aslinvoiceacr.azurecr.io` (`banda`, `bandb`, `mocks`, `bridge`) — MI pull |
| CAE | `asl-invoice-cae` (eastus2) |
| mocks | internal `http://mocks` (min 0) |
| **banda** | **https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/** (min 0, Azure SQL) |
| **bridge** | **https://bridge.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/** (Teams Bot `/api/messages`) |
| bandb | SB consumer via MI; KEDA on `invoice-review` + `sales-lead-qualification` (min 0) |
| Service Bus Basic | `aslinvoicebus` |
| Storage | `aslinvc54vfhn3oyovw` / `documents` |
| Key Vault | `asl-invoice-kvc54vfhn3oy` (`sql-admin-password`, `database-url`, `broker-hmac-secret`) |
| SQL Basic | `aslsqlcanadace.database.windows.net` / `asl_invoice` (canadacentral) — **wired** |
| MI | `asl-invoice-mi` on banda / bandb / mocks / bridge |
| Budget | `asl-invoice-30` ($30/mo) |
| Bot | `BandASalesBot` → `https://bridge…/api/messages` |

## Done (2026-09-29)

1. **SQL** — ODBC 18 in images; `DATABASE_URL` from Key Vault; schema created; empty leads confirms SQL (not SQLite seed).
2. **Zoho cutover** — Deluge → banda HTTPS direct (`docs/zoho_deluge_live_invoice.md`). Paste Script B in Zoho and Save.
3. **Teams cutover** — Bot endpoint → Azure `bridge` (no ngrok). Bridge → banda.
4. **Scale-to-zero** — banda / bandb / mocks / bridge `minReplicas=0`; bandb KEDA on both queues.

## Broker HMAC (T5) + queueing (Plan 3A)

- **Broker secret** — Key Vault `broker-hmac-secret` is wired to ACA `bandb` and `mocks` as `BROKER_HMAC_SECRET=secretref:broker-hmac-secret`. Band B mints short-lived `b1.*` tokens; mocks verify with the same secret. Local emulator keeps the lab default secret for convenience; Azure never uses that placeholder.
- **`ALWAYS_QUEUE=true`** — intentional. Band A always durable-handoffs to Service Bus. Teams gets a fast ack (“investigating…”) then the bridge **polls** `/finding` and replies when ready — not a same-HTTP-connection Band B result (cold-start friendly Azure shape).

## Manual step for you

Update Zoho Mail Deluge invoke URL to the Azure Script B in `docs/zoho_deluge_live_invoice.md` (one paste in Zoho UI — cannot be done from CLI).

## Optional later

- Disable ACR admin user
- Move JWT / bridge keys into Key Vault secretly
- CASE end-to-end smoke on Azure after Deluge paste
