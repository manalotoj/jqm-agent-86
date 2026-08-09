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
- Chat requests may include `metadata.artifact_ids` to attach previously uploaded session artifacts.
- Current attachment support validates ownership/session membership and persists normalized artifact IDs on the user message; it does not yet inject artifact file content into model prompts.
- If a dev or e2e Cosmos account is missing the artifacts metadata container, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/cosmos_db/add_artifacts_container.zsh --resource-group <rg> --account-name <cosmos-account>` to create `artifacts` with partition key `/session_id`.
- To provision dedicated Azure Blob Storage for artifact uploads in dev/e2e, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_storage/create_artifact_blob_storage.zsh --resource-group <rg>`. The helper creates one StorageV2 account per environment plus the `agent86-artifacts` container by default.
- To print the storage env values later with the account key redacted, use `/Users/johnmanaloto/source/github/jqm-agent-86/common/scripts/azure_storage/print_artifact_blob_env.zsh --resource-group <rg> --account-name <storage-account-name>`. Add `--show-secrets` only when you intentionally need the raw connection string for a local env file.
- When storing a real `AZURE_BLOB_CONNECTION_STRING` in `.env.api` or `.env.e2e`, wrap the value in single quotes because the local shell loader sources env files directly and Azure connection strings contain semicolons.

The Streamlit UI requires these variables at runtime:

- `ENTRA_UI_CLIENT_ID`
- `ENTRA_UI_CLIENT_SECRET`
- `ENTRA_REDIRECT_URI`

There is no authentication bypass mode.

When you use `zsh scripts/start_local.zsh`, the script loads:

- `.env.common` + `.env.api` for the FastAPI process
- `.env.common` + `.env.ui` for the Streamlit process

If one or more files do not exist, the script falls back to already-exported environment variables.

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