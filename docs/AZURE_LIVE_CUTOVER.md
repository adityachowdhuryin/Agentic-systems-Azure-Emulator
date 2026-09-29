# Live doors cutover (Zoho + Teams → Azure)

## Zoho Mail (direct — no ngrok)

1. Open Zoho Mail filter Deluge for the invoice inbox.
2. Paste Script B from `docs/zoho_deluge_live_invoice.md` (Azure URL + `X-Mail-Bridge-Key`).
3. Save. Send a pack JSON attachment to the monitored inbox.
4. Confirm on https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/

Health: `GET https://banda…/api/v1/webhooks/zoho-mail/health`

## Teams (Bot Framework needs the Node bridge)

Azure Bot cannot call Band A’s plain webhook — it needs `/api/messages` (Bot Framework).
The `bridge` Container App hosts that adapter and forwards to banda.

| Setting | Value |
| --- | --- |
| Bot | `BandASalesBot` (RG `Ai-Agent`) |
| Messaging endpoint | `https://bridge.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/api/messages` |
| Bridge → Band A | `BAND_A_URL=https://banda.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io` |
| Bridge health | https://bridge.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/health |

After bridge deploy, verify:

```bash
az bot show -g Ai-Agent -n BandASalesBot --query properties.endpoint -o tsv
curl -sS "https://bridge.calmdesert-93d3b4f1.eastus2.azurecontainerapps.io/health"
```

In Teams: message the bot (invoice CASE text or sales lead). Bot replies with run id; finding follows when bandb finishes.

## Retire local tunnel

Once both doors work on Azure: stop `ngrok` and Desktop `~/Desktop/webhook` for demos.
Keep the Desktop folder for local-only development.
