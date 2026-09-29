#!/usr/bin/env bash
# Requires User Access Administrator (or Owner) on Ai-Agent.
# Assign MI roles after foundation deploy.
set -euo pipefail
RG="${RG:-Ai-Agent}"
OUT=$(az deployment group show -g "$RG" -n asl-invoice-foundation --query properties.outputs -o json)
MI_PID=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['managedIdentityPrincipalId']['value'])")
ACR=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['acrLoginServer']['value'].split('.')[0])")
STG=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['storageAccountName']['value'])")
SB=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['serviceBusNamespace']['value'])")
KV=$(echo "$OUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['keyVaultName']['value'])")

az role assignment create --assignee-object-id "$MI_PID" --assignee-principal-type ServicePrincipal \
  --role "AcrPull" --scope "$(az acr show -n "$ACR" -g "$RG" --query id -o tsv)"
az role assignment create --assignee-object-id "$MI_PID" --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" --scope "$(az storage account show -n "$STG" -g "$RG" --query id -o tsv)"
az role assignment create --assignee-object-id "$MI_PID" --assignee-principal-type ServicePrincipal \
  --role "Azure Service Bus Data Owner" --scope "$(az servicebus namespace show -n "$SB" -g "$RG" --query id -o tsv)"
az role assignment create --assignee-object-id "$MI_PID" --assignee-principal-type ServicePrincipal \
  --role "Key Vault Secrets User" --scope "$(az keyvault show -n "$KV" -g "$RG" --query id -o tsv)"
echo "Role assignments done for MI $MI_PID"
