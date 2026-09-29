# Message for Anuj — Foundry access for lab MI (Band B 403)

Band B on Azure gets **Error code: 403** calling Foundry because managed identity
`asl-invoice-mi` has no model permission on `anujthakur-3048-resource`.

Aditya cannot assign this role (ABAC blocks `roleAssignments/write`).

## Please run (after MFA login)

```bash
az logout
az login --tenant b2d81262-a54d-4cb7-9406-06efbd98a5f8
az account set --subscription 0eb64859-ea04-452d-af53-90d2bee3b628

MI_PID=$(az identity show -g Ai-Agent -n asl-invoice-mi --query principalId -o tsv)
FOUNDRY=$(az cognitiveservices account show -g Ai-Agent -n anujthakur-3048-resource --query id -o tsv)

az role assignment create \
  --assignee-object-id "$MI_PID" \
  --assignee-principal-type ServicePrincipal \
  --role "Cognitive Services OpenAI User" \
  --scope "$FOUNDRY"

# Optional but useful:
az role assignment create \
  --assignee-object-id "$MI_PID" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure AI Developer" \
  --scope "$FOUNDRY"

az role assignment create \
  --assignee-object-id "$MI_PID" \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "$FOUNDRY/projects/anujthakur-3048"
```

Or re-run the updated `azure/infra/anuj-grant-access.sh` (now includes Foundry roles).

After this, Aditya will redeploy/retry the invoice run — Band B should get past the model call.
