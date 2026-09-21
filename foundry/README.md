# Microsoft Foundry SDK — local starter

Uses **Azure AI Projects 2.x** (`azure-ai-projects>=2.3.0`) + `azure-identity`.

## One-time setup

1. **Azure CLI** (for `az login` / `DefaultAzureCredential`) is installed at:

   ```bash
   ~/.local/bin/az
   # ensure PATH (already added to ~/.zshrc if missing):
   export PATH="$HOME/.local/bin:$PATH"
   ```

2. **Sign in:**

   ```bash
   az login
   az account show
   ```

3. **Create / open a Foundry project** in the portal and note:
   - **Project endpoint** — `https://<account>.services.ai.azure.com/api/projects/<project>`
   - **Model deployment name** — Models + endpoints → Name column

4. **Env file:**

   ```bash
   cp .env.example .env
   # edit FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_NAME
   ```

5. **Python packages** (Foundry SDK 2.x — separate from the az-cli venv):

   ```bash
   # already created:
   .venv/bin/pip show azure-ai-projects   # must be >= 2.3.0 (currently 2.6.x)
   ```

## Smoke test

```bash
cd foundry
.venv/bin/python smoke_test.py
```

You should see a model reply containing `foundry-sdk-ok`.

## Auth notes

- Entra ID only — no API key on `AIProjectClient`.
- Grant your user a Foundry role on the project (e.g. **Azure AI User**) via IAM.
- If auth fails, re-run `az login` and confirm `az account show` is the right subscription.

## Important

Keep **two Pythons / venvs**:

| Env | Purpose | Package |
|---|---|---|
| `foundry/.venv` | Foundry app code | `azure-ai-projects` **2.x** |
| `~/.local/az-cli-venv` | Azure CLI only | pulls `azure-ai-projects` 1.x as a dep — **do not** mix |

2.x is incompatible with 1.x (as noted in the Foundry docs).
