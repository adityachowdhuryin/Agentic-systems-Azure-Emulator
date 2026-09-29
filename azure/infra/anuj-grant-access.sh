#!/usr/bin/env bash
# =============================================================================
# Anuj — grant remaining ASL Invoice lab access (after interactive MFA login)
# =============================================================================
# Prerequisites (MUST do first in THIS terminal — MFA required):
#
#   az logout
#   az login --tenant b2d81262-a54d-4cb7-9406-06efbd98a5f8
#   az account set --subscription 0eb64859-ea04-452d-af53-90d2bee3b628
#
# Then:
#
#   chmod +x azure/infra/anuj-grant-access.sh
#   ./azure/infra/anuj-grant-access.sh
#
# What this script assigns (things Anuj can normally do after MFA):
#   - Aditya → Key Vault Secrets Officer on lab KV
#   - MI asl-invoice-mi → AcrPull, Storage Blob Data Contributor,
#                         Azure Service Bus Data Owner, Key Vault Secrets User
#
# What this script does NOT require Anuj to succeed at:
#   - User Access Administrator (often blocked by ABAC on sponsorship).
#     Skip with SKIP_UAA=1 (default). Set SKIP_UAA=0 to attempt it.
#
# Failures are printed (no 2>/dev/null). Exit code non-zero if any required
# assignment fails.
# =============================================================================
set -euo pipefail

SUB="${SUB:-0eb64859-ea04-452d-af53-90d2bee3b628}"
RG="${RG:-Ai-Agent}"
ADITYA_UPN="${ADITYA_UPN:-aditya.chowdhury@giantleapsystems.com}"
MI_NAME="${MI_NAME:-asl-invoice-mi}"
ACR_NAME="${ACR_NAME:-aslinvoiceacr}"
SB_NAME="${SB_NAME:-aslinvoicebus}"
FOUNDRY_ACCOUNT="${FOUNDRY_ACCOUNT:-anujthakur-3048-resource}"
FOUNDRY_PROJECT="${FOUNDRY_PROJECT:-anujthakur-3048}"
SKIP_UAA="${SKIP_UAA:-1}"

FAILED=0

echo "=== Preflight ==="
echo "Subscription: $SUB"
echo "Resource group: $RG"
echo "Assignee: $ADITYA_UPN"
echo "SKIP_UAA=$SKIP_UAA"
echo

az account set --subscription "$SUB"
ACCOUNT_UPN=$(az account show --query user.name -o tsv)
echo "Logged in as: $ACCOUNT_UPN"
echo "If you just got MFA / AADSTS50076 errors, run: az logout && az login --tenant b2d81262-a54d-4cb7-9406-06efbd98a5f8"
echo

# Resolve Aditya's object id
ADITYA_OID=$(az ad user show --id "$ADITYA_UPN" --query id -o tsv 2>/dev/null || true)
if [[ -z "${ADITYA_OID}" ]]; then
  ADITYA_OID=$(az ad user list --filter "mail eq '$ADITYA_UPN' or userPrincipalName eq '$ADITYA_UPN'" --query "[0].id" -o tsv)
fi
if [[ -z "${ADITYA_OID}" ]]; then
  echo "ERROR: could not resolve object id for $ADITYA_UPN"
  exit 1
fi
echo "Aditya object id: $ADITYA_OID"

RG_ID=$(az group show -n "$RG" --query id -o tsv)
MI_PID=$(az identity show -g "$RG" -n "$MI_NAME" --query principalId -o tsv)
ACR_ID=$(az acr show -g "$RG" -n "$ACR_NAME" --query id -o tsv)
SB_ID=$(az servicebus namespace show -g "$RG" -n "$SB_NAME" --query id -o tsv)
STG=$(az storage account list -g "$RG" --query "[?starts_with(name,'aslinv')].name | [0]" -o tsv)
STG_ID=$(az storage account show -g "$RG" -n "$STG" --query id -o tsv)
KV=$(az keyvault list -g "$RG" --query "[?starts_with(name,'asl-invoice-kv')].name | [0]" -o tsv)
KV_ID=$(az keyvault show -n "$KV" --query id -o tsv)
FOUNDRY_ID=$(az cognitiveservices account show -g "$RG" -n "$FOUNDRY_ACCOUNT" --query id -o tsv)
FOUNDRY_PROJ_ID="${FOUNDRY_ID}/projects/${FOUNDRY_PROJECT}"

echo "MI principal: $MI_PID"
echo "Storage: $STG"
echo "Key Vault: $KV"
echo "Foundry: $FOUNDRY_ACCOUNT / $FOUNDRY_PROJECT"
echo

# Returns 0 if role already present for this principal on this scope
already_has_role() {
  local oid="$1"
  local role="$2"
  local scope="$3"
  local count
  count=$(az role assignment list \
    --assignee-object-id "$oid" \
    --scope "$scope" \
    --role "$role" \
    --query "length(@)" -o tsv 2>/dev/null || echo 0)
  [[ "$count" != "0" && "$count" != "" ]]
}

assign() {
  local assignee_oid="$1"
  local principal_type="$2"
  local role="$3"
  local scope="$4"
  local required="${5:-1}"  # 1 = failure counts toward exit code

  echo "→ Assign '$role'"
  echo "  principalType=$principal_type  oid=$assignee_oid"
  echo "  scope=$scope"

  if already_has_role "$assignee_oid" "$role" "$scope"; then
    echo "  OK — already assigned (verified)"
    echo
    return 0
  fi

  local err
  set +e
  err=$(az role assignment create \
    --assignee-object-id "$assignee_oid" \
    --assignee-principal-type "$principal_type" \
    --role "$role" \
    --scope "$scope" \
    -o none 2>&1)
  local rc=$?
  set -e

  if [[ $rc -eq 0 ]]; then
    echo "  OK — created"
  else
    echo "  FAILED (exit $rc):"
    echo "$err" | sed 's/^/    /'
    if [[ "$required" == "1" ]]; then
      FAILED=1
    else
      echo "  (optional — continuing)"
    fi
  fi
  echo
}

if [[ "$SKIP_UAA" != "1" ]]; then
  echo "=== Optional: Aditya — User Access Administrator on RG ==="
  echo "(Often blocked by ABAC on sponsorship subscriptions.)"
  assign "$ADITYA_OID" User "User Access Administrator" "$RG_ID" 0
else
  echo "=== Skipping User Access Administrator (SKIP_UAA=1) ==="
  echo "If Aditya still needs UAA, a subscription Owner whose ABAC allows"
  echo "roleAssignments/write must grant it separately in Portal IAM."
  echo
fi

echo "=== Aditya — Key Vault Secrets Officer ==="
assign "$ADITYA_OID" User "Key Vault Secrets Officer" "$KV_ID" 1

echo "=== Managed identity data-plane roles (required) ==="
assign "$MI_PID" ServicePrincipal "AcrPull" "$ACR_ID" 1
assign "$MI_PID" ServicePrincipal "Storage Blob Data Contributor" "$STG_ID" 1
assign "$MI_PID" ServicePrincipal "Azure Service Bus Data Owner" "$SB_ID" 1
assign "$MI_PID" ServicePrincipal "Key Vault Secrets User" "$KV_ID" 1

echo "=== Managed identity → Foundry (fixes Band B model 403) ==="
assign "$MI_PID" ServicePrincipal "Cognitive Services OpenAI User" "$FOUNDRY_ID" 1
assign "$MI_PID" ServicePrincipal "Azure AI Developer" "$FOUNDRY_ID" 0
assign "$MI_PID" ServicePrincipal "Foundry User" "$FOUNDRY_PROJ_ID" 0

echo "=== Summary ==="
if [[ "$FAILED" -eq 0 ]]; then
  echo "All required role assignments succeeded (or were already present)."
  echo
  echo "Verify MI roles:"
  echo "  az role assignment list --assignee-object-id $MI_PID --all -o table"
  echo
  echo "Verify Aditya KV role:"
  echo "  az role assignment list --assignee $ADITYA_UPN --scope $KV_ID -o table"
  exit 0
fi

echo "One or more REQUIRED assignments failed."
echo
echo "If you saw AADSTS50076 (MFA):"
echo "  az logout"
echo "  az login --tenant b2d81262-a54d-4cb7-9406-06efbd98a5f8"
echo "  az account set --subscription $SUB"
echo "  ./azure/infra/anuj-grant-access.sh"
echo
echo "If User Access Administrator failed with ABAC: ignore it (SKIP_UAA=1)."
echo "A different Owner may need to grant UAA in Portal if Aditya still needs it."
exit 1
