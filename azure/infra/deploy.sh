#!/usr/bin/env bash
# Deploy foundation infra to Ai-Agent (eastus2). Requires Contributor + spend approval.
set -euo pipefail
RG="${RG:-Ai-Agent}"
LOC="${LOC:-eastus2}"
PREFIX="${PREFIX:-asl-invoice}"
SQL_PASS="${SQL_ADMIN_PASSWORD:-$(openssl rand -base64 24)}"

echo "Deploying foundation to $RG ($LOC)..."
az deployment group create \
  -g "$RG" \
  -n asl-invoice-foundation \
  -f "$(dirname "$0")/main.bicep" \
  -p location="$LOC" namePrefix="$PREFIX" sqlAdminPassword="$SQL_PASS" \
  -o table

echo "SQL admin password (store in Key Vault): $SQL_PASS"
az deployment group show -g "$RG" -n asl-invoice-foundation --query properties.outputs -o json
