#!/usr/bin/env bash
# Anuj / subscription Owner: run once on Sponsorship subscription.
# Without this, RG Contributor cannot create ACA/SQL/ACR/SB/KV/Storage.
set -euo pipefail
SUB="${1:-0eb64859-ea04-452d-af53-90d2bee3b628}"
az account set --subscription "$SUB"
for p in \
  Microsoft.App \
  Microsoft.ContainerRegistry \
  Microsoft.ServiceBus \
  Microsoft.Sql \
  Microsoft.KeyVault \
  Microsoft.Storage \
  Microsoft.OperationalInsights \
  Microsoft.Insights \
  Microsoft.ManagedIdentity
do
  echo "Registering $p ..."
  az provider register -n "$p" --wait
done
echo "Done. Verify:"
az provider list --query "[?contains('App|ContainerRegistry|ServiceBus|Sql|KeyVault|Storage', namespace)].{n:namespace,s:registrationState}" -o table
echo
echo "Also grant aditya.chowdhury@giantleapsystems.com User Access Administrator on RG Ai-Agent"
echo "so assign-roles.sh can attach the managed identity roles."
