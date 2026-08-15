# agent-86

agent-86 is a local-first, Azure-oriented AI agent backend built with FastAPI. It supports persistent chat sessions, message history stored in Azure Cosmos DB, first-class session artifacts stored in Azure Blob Storage with Cosmos-backed metadata, model routing between default and premium chat models, optional tool use for web search, and Microsoft Entra ID delegated user authentication for both the Streamlit UI and FastAPI API.

The repository also includes a Streamlit development UI that signs the user in with Microsoft Entra ID, acquires a delegated access token with OAuth 2.0 Authorization Code Flow, and calls the backend API with `Authorization: Bearer <access_token>`.

## Current Features

- FastAPI backend for chat-oriented workflows
- Session creation, listing, retrieval, update, and deletion
- Persistent message history per session
- Session artifact upload, listing, metadata retrieval, and download
- Chat endpoint that stores user and assistant messages
- Minimal chat attachment references via `metadata.artifact_ids`
- Model routing between configured default and premium models
- Optional web search tool support during chat
- Streamlit development UI for local testing
- Microsoft Entra ID Authorization Code Flow for interactive sign-in
- Backend bearer-token validation via OpenID metadata discovery and JWKS signing keys
- Per-user ownership enforcement for sessions and messages

## Azure Bicep conversion testing assets

The Azure Bicep conversion feature includes manual testing assets in `/Users/johnmanaloto/source/github/jqm-agent-86/docs`:

- API overview: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/azure-bicep-conversion-api.md`
- Manual testing guide: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/azure-bicep-conversion-manual-testing.md`
- Postman collection: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/postman/azure-bicep-conversion.postman_collection.json`
- Postman environment template: `/Users/johnmanaloto/source/github/jqm-agent-86/docs/postman/azure-bicep-conversion.local.postman_environment.json`

## Architecture Summary

- **FastAPI** provides the HTTP API surface and request orchestration
- **Azure Cosmos DB** stores sessions, messages, and artifact metadata
- **Azure Blob Storage** stores uploaded artifact file contents
- **Azure OpenAI / Foundry-compatible API access** powers chat completions
- **Service layer orchestration** keeps routing, chat, and persistence logic separated
- **Tool abstraction layer** allows the model to invoke tools such as web search
- **Microsoft Entra ID** issues delegated user access tokens for the backend API
- **Streamlit** provides a local authenticated chat interface for development

## Project Structure

```text
src/agent_86/
  api/            FastAPI routes and dependency wiring
  core/           configuration and settings
  domain/         domain models and API schemas
  repositories/   persistence implementations
  services/       application orchestration and business logic
  tools/          tool interfaces, registry, and implementations
src/tests/        tests
dev_ui.py         Streamlit development UI
docs/             decision records and implementation planning
scripts/          helper scripts, including local Cosmos DB setup
```

## Current Runtime Behavior

At a high level, the application works like this:

1. The Streamlit UI redirects an unauthenticated user to Microsoft Entra ID.
2. Microsoft Entra ID returns an authorization code to the configured Streamlit redirect URI.
3. The UI exchanges the code for delegated tokens with MSAL and caches/refreshes them for the current Streamlit session.
4. The UI calls the FastAPI backend with `Authorization: Bearer <access_token>`.
5. The API validates the bearer token against Microsoft identity platform metadata and signing keys.
6. The API resolves the authenticated user identity from `oid` or falls back to `sub`.
7. Sessions and messages are filtered by `user_id`, and cross-user access returns `404`.
8. Chat requests persist the user message, run model/tool orchestration, and persist transcript plus assistant output.

## Requirements

- Python 3.12+
- An Azure Cosmos DB account, emulator, or equivalent reachable endpoint
- An Azure Blob Storage account/container reachable from the backend
- An Azure OpenAI / Foundry-compatible chat endpoint
- A Microsoft Entra tenant with two app registrations (UI and backend API)
- Optional Tavily or Brave Search API key for web search support

## Configuration

The app code reads configuration from environment variables.

For local development, this repo uses split env files that are loaded by `scripts/start_local.zsh`:

- `.env.common` for values shared by API and UI
- `.env.api` for FastAPI-only settings
- `.env.ui` for Streamlit-only settings

Important settings include:

- `APP_NAME`
- `APP_ENV`
- `COSMOS_ENDPOINT`
- `COSMOS_KEY`
- `COSMOS_DATABASE_NAME`
- `COSMOS_SESSIONS_CONTAINER_NAME`
- `COSMOS_MESSAGES_CONTAINER_NAME`
- `COSMOS_ARTIFACTS_CONTAINER_NAME`
- `COSMOS_SUMMARIES_CONTAINER_NAME`
- `COSMOS_VERIFY_SSL`
- `AZURE_BLOB_CONNECTION_STRING`
- `AZURE_BLOB_CONTAINER_NAME`
- `FOUNDRY_OPENAI_BASE_URL`
- `FOUNDRY_OPENAI_API_KEY`
- `FOUNDRY_DEFAULT_CHAT_MODEL`
- `FOUNDRY_PREMIUM_CHAT_MODEL`
- `AZURE_OPENAI_VERIFY_SSL`
- `ENTRA_TENANT_ID`
- `ENTRA_API_CLIENT_ID`
- `ENTRA_API_AUDIENCE`
- `ENTRA_UI_CLIENT_ID` *(UI only)*
- `ENTRA_UI_CLIENT_SECRET` *(UI only)*
- `ENTRA_REDIRECT_URI` *(UI only)*
- `TAVILY_API_KEY` *(optional)*
- `BRAVE_SEARCH_API_KEY` *(optional)*
- `WEB_SEARCH_TIMEOUT_SECONDS`
- `WEB_SEARCH_MAX_RESULTS`

See `src/agent_86/core/config.py` for the full set of supported settings.

## Microsoft Entra ID Setup

This project uses **two separate Microsoft Entra app registrations**.

### App registration 1: Streamlit UI

Purpose: interactive user sign-in.

- Platform: **Web**
- Client type: **confidential client**
- Flow: **OAuth 2.0 Authorization Code Flow** via MSAL Python
- Redirect URI (local development):

  ```text
  http://localhost:8501/
  ```

  > Do **not** use `http://localhost:8501/oauth2callback` for this custom MSAL flow. Streamlit reserves `/oauth2callback` for its built-in `st.login()`/OIDC handler, so Entra callbacks to that path never reach `dev_ui.py`.

- Client secret: required
- Delegated API permission to the backend API scope:

  ```text
  api://<backend-client-id>/access_as_user
  ```

Do not add Microsoft Graph permissions unless the UI actually needs Graph.

### App registration 2: FastAPI backend API

Purpose: protect API endpoints.

- Supported account types: **Accounts in this organizational directory only**
- Tenant mode: **single tenant**
- Expose an API with:

  ```text
  Application ID URI: api://<backend-client-id>
  Scope name: access_as_user
  Full scope: api://<backend-client-id>/access_as_user
  ```

The Streamlit UI requests that delegated scope during sign-in.

### Authentication behavior in this repo

- The Streamlit UI uses MSAL's authorization-code flow support.
- The UI keeps one long-lived MSAL client per Streamlit session.
- Access tokens are refreshed before expiry when possible.
- Backend requests retry once after a `401` with a refreshed token.
- The FastAPI API validates bearer tokens using OpenID Connect metadata and JWKS keys from Microsoft Entra ID.
- The backend resolves the user identity from `oid`, falling back to `sub` only when `oid` is absent.
- The backend refuses startup when required auth configuration is missing.

## Local Development

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure local environment files

Create these files in the repository root:

- `.env.common`
- `.env.api`
- `.env.ui`

You can copy from the checked-in examples:

```bash
cp .env.common.example .env.common
cp .env.api.example .env.api
cp .env.ui.example .env.ui
```

#### `.env.common`

Shared settings used by both the FastAPI API and the Streamlit UI:

```env
APP_NAME=agent-86
APP_ENV=dev
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

ENTRA_TENANT_ID=your-tenant-id
ENTRA_API_CLIENT_ID=your-backend-api-app-client-id
ENTRA_API_AUDIENCE=api://your-backend-api-app-client-id
```

#### `.env.api`

Backend-only settings:

```env
COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=agent86
COSMOS_SESSIONS_CONTAINER_NAME=sessions
COSMOS_MESSAGES_CONTAINER_NAME=messages
COSMOS_ARTIFACTS_CONTAINER_NAME=artifacts
COSMOS_SUMMARIES_CONTAINER_NAME=summaries

AZURE_BLOB_CONNECTION_STRING='your-azure-blob-connection-string'
AZURE_BLOB_CONTAINER_NAME=agent86-artifacts

FOUNDRY_OPENAI_BASE_URL=https://your-foundry-or-openai-endpoint/
FOUNDRY_OPENAI_API_KEY=your-openai-or-foundry-key
FOUNDRY_DEFAULT_CHAT_MODEL=gpt-4.1-mini
FOUNDRY_PREMIUM_CHAT_MODEL=gpt-5.4

TAVILY_API_KEY=
BRAVE_SEARCH_API_KEY=
```

#### `.env.ui`

UI-only settings:

```env
ENTRA_UI_CLIENT_ID=your-streamlit-ui-app-client-id
ENTRA_UI_CLIENT_SECRET=your-streamlit-ui-client-secret
ENTRA_REDIRECT_URI=http://localhost:8501/
API_BASE_URL=http://127.0.0.1:8000
```

The backend requires these authentication variables at startup:

- `ENTRA_TENANT_ID`
- `ENTRA_API_CLIENT_ID`
- `ENTRA_API_AUDIENCE`

The backend also requires storage configuration at startup:

- `COSMOS_ENDPOINT`
- `COSMOS_KEY`
- `COSMOS_DATABASE_NAME`
- `AZURE_BLOB_CONNECTION_STRING`
- `AZURE_BLOB_CONTAINER_NAME`

Artifact behavior notes:

- Artifact binary content is stored in Azure Blob Storage.
- Artifact metadata is stored in Cosmos DB in a dedicated artifacts container.
- Session summaries are stored in Cosmos DB in a dedicated summaries container.
- Chat requests may include `metadata.artifact_ids` to attach previously uploaded session artifacts.
- Supported text attachments are injected into model context at chat time using full-content, head+tail, or truncated excerpts depending on size.
- When only partial attachment content is provided, the model is instructed to disclose that limitation in its answer.
- Unsupported or unreadable attachments are surfaced to the model as unreadable notes rather than silently ignored.
- If a dev or e2e Cosmos account is missing the artifacts metadata container, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/cosmos_db/add_artifacts_container.zsh --resource-group <rg> --account-name <cosmos-account>` to create `artifacts` with partition key `/session_id`.
- If a dev or e2e Cosmos account is missing the summaries container, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/cosmos_db/add_summaries_container.zsh --resource-group <rg> --account-name <cosmos-account>` to create `summaries` with partition key `/user_id`, or use `--all-dev-accounts` to apply the same container to every Cosmos account in `rg-agent86-dev`.
- To provision dedicated Azure Blob Storage for artifact uploads in dev/e2e, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_storage/create_artifact_blob_storage.zsh --resource-group <rg>`. The helper creates one StorageV2 account per environment plus the `agent86-artifacts` container by default.
- To print the storage env values later with the account key redacted, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_storage/print_artifact_blob_env.zsh --resource-group <rg> --account-name <storage-account-name>`. Add `--show-secrets` only when you intentionally need the raw connection string for a local env file.
- When storing a real `AZURE_BLOB_CONNECTION_STRING` in `.env.api` or `.env.e2e`, wrap the value in single quotes because the local shell loader sources env files directly and Azure connection strings contain semicolons.

Session summary API notes:

- `POST /sessions/{session_id}/summary` always regenerates and overwrites the stored summary for that session.
- `GET /sessions/{session_id}/summary` returns `404` when no summary has been generated yet.
- Summary generation uses the configured chat model with tools disabled and stores one summary per session.

The Streamlit UI requires these variables at runtime:

- `ENTRA_UI_CLIENT_ID`
- `ENTRA_UI_CLIENT_SECRET`
- `ENTRA_REDIRECT_URI`

There is no authentication bypass mode.

When you use `zsh scripts/start_local.zsh`, the script loads:

- `.env.common` + `.env.api` for the FastAPI process
- `.env.common` + `.env.ui` for the Streamlit process

If one or more files do not exist, the script falls back to already-exported environment variables.

### Local env files and GitHub Actions can coexist

This repo intentionally supports both:

- local developer runs using local env files such as `backend/.env.api`
- GitHub Actions deployment workflows using GitHub Environment secrets plus Azure Key Vault

The application config contract stays the same in both cases. The difference is only where the values come from.

For local development:

- keep using your normal local `backend/.env.api`
- keep using local `frontend/.env.*` files as needed

For GitHub Actions:

- the `Infra Dev` workflow can materialize `backend/.env.api` inside the runner from the GitHub Environment secret `BACKEND_ENV_API_DEV`
- after materializing that file, the workflow imports the allowlisted values into Azure Key Vault
- if `BACKEND_ENV_API_DEV` is not set, the workflow falls back to an existing `backend/.env.api` file in the workspace
- if neither exists, the Key Vault import step is skipped with a clear workflow summary message

Recommended setup for the `dev` GitHub Environment:

- OIDC / Azure login secrets:
  - `AZURE_CLIENT_ID`
  - `AZURE_TENANT_ID`
  - `AZURE_SUBSCRIPTION_ID`
- backend env content secret:
  - `BACKEND_ENV_API_DEV`

Example `BACKEND_ENV_API_DEV` secret value:

```env
FOUNDRY_OPENAI_API_KEY=your-foundry-or-openai-key
TAVILY_API_KEY=
BRAVE_SEARCH_API_KEY=
```

Only include values that you want the Key Vault import helper to ingest. Infra-managed values such as Cosmos keys, blob connection strings, Application Insights connection strings, and the Static Web App deployment token are reconciled directly by the workflow and stored in Key Vault automatically.

### 3. Start both the API and UI together

From the repository root:

```bash
zsh scripts/start_local.zsh
```

The helper script:

- prefers the repo-local `.venv` when present
- starts the FastAPI API on `http://127.0.0.1:8000`
- starts the Streamlit UI on `http://127.0.0.1:8501`
- expects valid Entra configuration for both backend and UI
- stops both processes when you press `Ctrl+C`

### 4. Run them manually instead

If you prefer separate terminals, load the same env files yourself before starting each process.

#### FastAPI backend

```bash
set -a
source .env.common
source .env.api
set +a
PYTHONPATH=src uvicorn agent_86.main:app --reload
```

#### Streamlit development UI

In another terminal:

```bash
set -a
source .env.common
source .env.ui
set +a
streamlit run dev_ui.py
```

### Optional: run the MCP stdio server

Install the optional MCP dependency without changing the core app requirements:

```bash
pip install -r requirements.txt -r requirements-mcp.txt
```

Then start the stdio MCP server from the repository root:

```bash
zsh scripts/start_mcp.zsh
```

This exposes the same registered tool layer used by agent-86's chat workflow, currently `web_search`, over MCP for local clients such as Cline.

> **Context note:** MCP-originated tool calls use a deliberate synthetic `ToolContext` of `session_id="mcp-stdio"`, `user_id="mcp-client"`, and `metadata={"origin": "mcp", "transport": "stdio"}` because these calls do not originate from an agent-86 chat session.

> **Future auth note:** stdio is sufficient for Phase 1 and local machine credentials, but it does not carry end-user delegated identity. If future Azure inspection tools require per-user delegated auth, a later transport/auth design will need to account for that.

#### Cline MCP config

Add this block to Cline's MCP server settings:

```json
{
  "mcpServers": {
    "agent-86": {
      "command": "/bin/zsh",
      "args": [
        "-lc",
        "cd /Users/johnmanaloto/source/github/jqm-agent-86 && zsh scripts/start_mcp.zsh"
      ]
    }
  }
}
```

The helper script already prefers the repo-local `.venv` when present, so you usually do not need to hardcode a Python interpreter into the Cline config.

## Azure Deployment

This repository now includes Azure CLI + zsh helpers for provisioning and deploying the current app stack into Azure.

### Target Azure shape

The current dev hosting target is a shared resource group with:

- 1 Azure Container Registry (ACR)
- 1 Log Analytics Workspace (LAW)
- 1 shared Azure Container Apps Environment (ACAE)
- 1 external Container App for the FastAPI backend
- 1 internal Container App for the .NET Bicep composition API
- 1 Azure Static Web App (SWA) for the frontend
- 1 optional internal Container App for the MCP server

Default dev names:

- Resource group: `rg-agent86-dev`
- ACR: `acragent86dev`
- Log Analytics Workspace: `law-agent86-dev`
- Container Apps environment: `acae-agent86-dev`
- Static Web App: `swa-agent86-dev`
- API app: `aca-agent86-api-dev`
- MCP app: `aca-agent86-mcp-dev`
- Tooling app: `aca-agent86-tooling-dev`

### Container images and Dockerfiles

The deployment helpers now assume these checked-in Dockerfiles by default:

- API: `/Users/johnmanaloto/source/github/jqm-agent-86/backend/Dockerfile.api`
- MCP: `/Users/johnmanaloto/source/github/jqm-agent-86/backend/Dockerfile.mcp`
- Tooling: `/Users/johnmanaloto/source/github/jqm-agent-86/tooling/bicep-composition-service/Dockerfile`

Image defaults used by the deploy script:

- `agent86-api`
- `agent86-mcp`
- `agent86-tooling`

### Provision shared Azure hosting resources

First create or reuse the shared hosting resources in the target resource group:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_deploy/provision_agent86_dev_hosting.zsh \
  --resource-group rg-agent86-dev
```

That helper provisions or reuses:

- Azure Container Registry
- Log Analytics Workspace
- Azure Container Apps Environment
- Azure Static Web App

You must already be logged into Azure CLI:

```bash
az login
az account show
```

### GitHub Actions deployment flow

The repository includes these GitHub workflows for Azure dev automation:

- `/Users/johnmanaloto/source/github/jqm-agent-86/.github/workflows/infra-dev.yml`
- `/Users/johnmanaloto/source/github/jqm-agent-86/.github/workflows/deploy-backend-dev.yml`
- `/Users/johnmanaloto/source/github/jqm-agent-86/.github/workflows/deploy-frontend-dev.yml`

Current behavior:

- `infra-dev.yml` reconciles or reuses the required Azure dev resources
- it fails on ambiguous Azure resource discovery instead of silently picking the first match
- it stores normalized runtime secrets in Key Vault, including:
  - `cosmos-key`
  - `applicationinsights-connection-string`
  - `azure-blob-connection-string`
  - `azure-static-web-app-deployment-token`
- it can also import additional backend secrets from `BACKEND_ENV_API_DEV` via a temporary `backend/.env.api` file in the runner workspace
- `deploy-backend-dev.yml` reads deployment secrets from Key Vault and deploys the backend Container Apps
- `deploy-frontend-dev.yml` reads the Static Web App deployment token from Key Vault and deploys the frontend

This means you do not have to choose between local development and GitHub-based Azure deployment. Local files remain the developer experience, while GitHub Environment secrets and Key Vault back the shared Azure deployment path.

### First-time GitHub setup checklist

Use this checklist before your first real GitHub-hosted Azure deployment.

#### 1. Create or choose an Azure identity for GitHub OIDC

Create an Azure app registration or user-assigned managed identity that GitHub Actions will use to log into Azure.

Required values to capture for GitHub:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`

That identity must have enough RBAC in the target subscription or resource group to:

- create or update resource groups and app hosting resources when needed
- read and write Key Vault secrets
- read Cosmos DB keys
- read Static Web App secrets
- deploy Container Apps and related resources

At minimum, make sure it can manage the target dev resource group and any resources created within it.

#### 2. Add the GitHub OIDC federated credential

Configure a federated credential on the Azure identity that trusts this GitHub repository and the branch or environment you want to deploy from.

Typical trust inputs:

- GitHub organization/user
- repository name
- branch or environment condition

The workflows already use:

```yaml
permissions:
  id-token: write
  contents: read
```

so once the Azure federated credential is configured correctly, `azure/login@v2` can exchange the GitHub OIDC token for Azure access without storing a client secret in GitHub.

#### 3. Create the GitHub `dev` Environment

In the repository settings, create an Environment named `dev`.

Add these required secrets:

- `AZURE_CLIENT_ID`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `BACKEND_ENV_API_DEV`

Add these required environment variables used by the deploy workflows:

- `ENTRA_TENANT_ID`
- `ENTRA_API_CLIENT_ID`
- `ENTRA_API_AUDIENCE`
- `FOUNDRY_OPENAI_BASE_URL`
- `FOUNDRY_DEFAULT_CHAT_MODEL`
- `FOUNDRY_PREMIUM_CHAT_MODEL`
- `VITE_ENTRA_CLIENT_ID`
- `VITE_ENTRA_TENANT_ID`
- `VITE_API_SCOPE`

Recommended notes:

- keep `BACKEND_ENV_API_DEV` limited to backend secrets that should be imported into Key Vault
- do not put Azure infrastructure-generated secrets there when the workflow already reconciles them directly
- consider using GitHub Environment protection rules if you want approvals before deployment

#### 4. Confirm Azure naming expectations

By default, the workflows assume the dev resource group is:

- `rg-agent86-dev`

and expect the reconciled resources to follow the current single-resource-per-type model in that group.

If you intentionally use different names, run the infra workflow first and verify the created resources match your intended layout.

#### 5. Recommended first workflow run order

Run the workflows in this order for a new environment:

1. `Infra Dev`
   - creates or reuses hosting resources
   - reconciles Cosmos DB, Storage, Application Insights, Key Vault, and Static Web App metadata
   - stores normalized secrets in Key Vault
2. `Deploy Backend Dev`
   - reads runtime secrets from Key Vault
   - deploys the backend Container Apps
   - runs a backend smoke test
3. `Deploy Frontend Dev`
   - resolves the Static Web App hostname and deployment token
   - builds and uploads the frontend
   - runs a frontend smoke test

#### 6. Verify after the first run

After the first full run, verify:

- the `Infra Dev` workflow summary shows exactly one resolved Key Vault, Cosmos DB account, Storage account, Static Web App, and Application Insights resource
- Key Vault contains the expected secrets
- the backend health endpoint responds successfully
- the frontend loads and points at the deployed backend URL

If a workflow fails with an ambiguity error, it means the resource group contains multiple matching candidates and the workflow intentionally refused to guess.

### Deploy backend services to Azure Container Apps

The main service deployment helper builds images with Azure Container Registry Tasks and then creates or updates the Container Apps.

Default deployment, recommended for now:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_container_apps/deploy_agent86_services.zsh \
  --resource-group rg-agent86-dev
```

That deploys:

- FastAPI API as an external Container App on port `8000`
- Bicep composition tooling API as an internal Container App on port `8080`

It also injects this API environment wiring by default:

- `BICEP_COMPOSITION_BASE_URL=http://aca-agent86-tooling-dev`

To opt into MCP deployment as well:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_container_apps/deploy_agent86_services.zsh \
  --resource-group rg-agent86-dev \
  --deploy-mcp
```

When `--deploy-mcp` is used, the script also injects:

- `MCP_BASE_URL=http://aca-agent86-mcp-dev`

#### Important MCP caveat

The current MCP implementation is still stdio-oriented, not HTTP-native. That means:

- the MCP container image can be built
- the MCP Container App can be created if you explicitly request it
- but the current service shape may not behave like a normal HTTP service behind Container Apps

For that reason, `deploy_agent86_services.zsh` skips MCP by default and requires `--deploy-mcp` to include it.

### Supplying app configuration and secrets

The deploy helper supports repeatable env and secret flags per service:

- `--api-env KEY=VALUE`
- `--api-secret KEY=VALUE`
- `--tooling-env KEY=VALUE`
- `--tooling-secret KEY=VALUE`
- `--mcp-env KEY=VALUE`
- `--mcp-secret KEY=VALUE`

Example:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_container_apps/deploy_agent86_services.zsh \
  --resource-group rg-agent86-dev \
  --api-env APP_ENV=dev \
  --api-env CORS_ALLOWED_ORIGINS=https://example.com \
  --api-secret OPENAI_API_KEY=... \
  --tooling-env ASPNETCORE_ENVIRONMENT=Development
```

You will likely need to provide your real backend/runtime settings for:

- Entra auth
- Cosmos DB
- Blob Storage
- model configuration
- telemetry / monitoring
- any provider credentials used by tools

### Inspect deployed Container App URLs

After deployment, you can print useful values from a Container App:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_container_apps/print_container_app_env.zsh \
  --resource-group rg-agent86-dev \
  --app-name aca-agent86-api-dev
```

This prints values such as:

- `AZURE_CONTAINER_APP_NAME`
- `AZURE_CONTAINER_APP_FQDN`
- `AZURE_CONTAINER_APP_URL` for external ingress apps

Use the API URL from that output as the frontend's `VITE_API_BASE_URL`.

### Configure frontend build environment for Azure Static Web Apps

The frontend expects these Vite environment variables for Azure deployment:

- `VITE_ENTRA_CLIENT_ID`
- `VITE_ENTRA_TENANT_ID`
- `VITE_REDIRECT_URI`
- `VITE_API_SCOPE`
- `VITE_API_BASE_URL`

Use the helper to print them in the expected format:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_static_web_apps/print_frontend_deploy_env.zsh \
  --api-url https://<api-fqdn> \
  --redirect-uri https://<your-swa-hostname> \
  --tenant-id <entra-tenant-id> \
  --client-id <frontend-spa-client-id> \
  --api-scope <api-scope>
```

### Azure Static Web App deployment details

The shared hosting provisioner creates the Static Web App resource, but it does not publish frontend content for you.

Typical flow:

1. Provision the SWA resource.
2. Get the SWA hostname from Azure.
3. Generate frontend build env values using `print_frontend_deploy_env.zsh`.
4. Build and deploy the frontend using your preferred SWA deployment path.

If you need the SWA deployment token, the underlying helper supports printing it during creation:

```bash
zsh /Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_static_web_apps/create_static_web_app.zsh \
  --resource-group rg-agent86-dev \
  --name swa-agent86-dev \
  --show-deployment-token
```

### Post-deployment checklist

After the first Azure deploy, verify and update:

- backend CORS to include the Static Web App hostname
- Entra redirect URIs to include the Static Web App URL
- API app settings and secrets for Cosmos, Blob Storage, auth, and model providers
- internal service discovery assumptions for Container Apps internal URLs
- Azure CLI / Container Apps extension compatibility if `az containerapp update` behavior differs in your local environment

### Relevant deployment helpers

- `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_deploy/provision_agent86_dev_hosting.zsh`
- `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_container_apps/deploy_agent86_services.zsh`
- `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_container_apps/print_container_app_env.zsh`
- `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_static_web_apps/create_static_web_app.zsh`
- `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_static_web_apps/print_frontend_deploy_env.zsh`

### 5. Open the API docs

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## API Overview

### Health

- `GET /health` — basic service status

### Sessions

- `POST /sessions` — create a session
- `GET /sessions` — list sessions
- `GET /sessions/{session_id}` — get a single session
- `PATCH /sessions/{session_id}` — update a session title
- `DELETE /sessions/{session_id}` — delete a session and its messages

### Messages

- `POST /sessions/{session_id}/messages` — create a message directly
- `GET /sessions/{session_id}/messages` — list messages for a session

### Chat

- `POST /sessions/{session_id}/chat` — send a user prompt and receive a persisted assistant reply
- `POST /sessions/{session_id}/chat/stream` — stream chat events over Server-Sent Events

The chat endpoint currently:

- stores the incoming user message
- auto-titles default sessions from the prompt when appropriate
- selects a configured model tier
- optionally enables the web search tool
- stores tool transcript messages returned from the model workflow
- stores the final assistant message with model metadata

## Development UI

`dev_ui.py` is a Streamlit-based frontend that can:

- redirect unauthenticated users to Microsoft Entra ID
- receive the authorization code callback and exchange it for tokens
- cache and refresh delegated API access tokens
- list existing sessions
- create, rename, and delete sessions
- view session history
- choose a model for chat requests
- enable optional web search
- send prompts to the backend chat endpoint

Every backend request from the UI, including streaming chat requests, includes the delegated bearer token.

## Current Limitations

- The current tool set is minimal and focused on web search
- Web search only works when a provider key is configured and the request looks search-worthy
- Persistence depends on a reachable Cosmos DB endpoint and configured containers
- The backend is currently structured for single-tenant Entra validation; future multi-tenant support should only require auth configuration changes rather than business-logic changes

## Roadmap

Near-term focus areas still include:

- stronger prompt construction and routing rules
- better observability and smoke tests
- additional tool integrations such as Azure inspection and GitHub access
- future file upload, artifact storage, and generated output workflows
- additional production hardening beyond the current Entra auth baseline

## Additional Docs

- `docs/decisions.md`
- `docs/implementation-plan/roadmap.md`
- `scripts/cosmos_db/local_cosmosdb.zsh`
- `common/scripts/cosmos_db/add_artifacts_container.zsh`
- `common/scripts/azure_storage/create_artifact_blob_storage.zsh`
- `common/scripts/azure_storage/print_artifact_blob_env.zsh`
- `common/scripts/azure_storage/print_artifact_blob_env.zsh`

## Status

This repository now contains a working authenticated backend/UI slice with delegated Microsoft Entra ID sign-in, per-user resource ownership, and offline auth test coverage. The current focus is improving documentation, extending tools, and evolving the app toward a more production-capable Azure-native agent platform.