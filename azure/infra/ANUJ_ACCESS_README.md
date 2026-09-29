# Message for Anuj — remaining access (MFA + MI roles)

Please re-download / use the updated `anuj-grant-access.sh` (errors are no longer hidden).

## In your terminal (interactive MFA required)

```bash
az logout
az login --tenant b2d81262-a54d-4cb7-9406-06efbd98a5f8
az account set --subscription 0eb64859-ea04-452d-af53-90d2bee3b628

cd "<path-to-Azure-Emulator>"   # or run the script from Downloads
bash anuj-grant-access.sh
# or:  bash azure/infra/anuj-grant-access.sh
```

## What we need from you

**Required (after MFA):** assign these to managed identity `asl-invoice-mi` on RG `Ai-Agent`:

| Role | Scope |
| --- | --- |
| AcrPull | ACR `aslinvoiceacr` |
| Storage Blob Data Contributor | storage `aslinv…` |
| Azure Service Bus Data Owner | `aslinvoicebus` |
| Key Vault Secrets User | `asl-invoice-kv…` |

Also: **Key Vault Secrets Officer** for `aditya.chowdhury@giantleapsystems.com` on that Key Vault.

**Optional / often blocked by ABAC:** User Access Administrator for Aditya on RG `Ai-Agent`.  
The updated script **skips** that by default (`SKIP_UAA=1`). If Aditya still needs UAA, a subscription Owner whose ABAC allows `roleAssignments/write` must grant it in Portal IAM — your session cannot.

## Do not

- Do not rely on “already assigned” without verifying — the old script hid Azure errors with `2>/dev/null`.
