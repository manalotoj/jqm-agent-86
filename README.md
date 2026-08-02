# agent-86

agent-86 is a local-first, Azure-oriented AI agent backend built with FastAPI. It supports persistent chat sessions, message history stored in Azure Cosmos DB, model routing between default and premium chat models, and optional tool use for web search.

The repository also includes a lightweight Streamlit development UI for exercising the API locally.

## Current Features

- FastAPI backend for chat-oriented workflows
- Session creation, listing, retrieval, update, and deletion
- Persistent message history per session
- Chat endpoint that stores user and assistant messages
- Model routing between configured default and premium models
- Optional web search tool support during chat
- Streamlit development UI for local testing

## Architecture Summary

- **FastAPI** provides the HTTP API surface and request orchestration
- **Azure Cosmos DB** stores sessions and messages
- **Azure OpenAI / Foundry-compatible API access** powers chat completions
- **Service layer orchestration** keeps routing, chat, and persistence logic separated
- **Tool abstraction layer** allows the model to invoke tools such as web search
- **Streamlit** provides a simple local chat interface for development

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

1. A client creates or selects a chat session.
2. Messages are stored in Azure Cosmos DB.
3. A chat request is posted to `/sessions/{session_id}/chat`.
4. The API persists the user message and may derive a session title from the first prompt.
5. The request metadata is used to choose the configured model tier.
6. If enabled and relevant, the API makes the `web_search` tool available to the model.
7. The model generates a response, optionally invoking tools through the tool service.
8. Tool transcript messages and the final assistant reply are persisted.

## Requirements

- Python 3.12+
- An Azure Cosmos DB account, emulator, or equivalent reachable endpoint
- An Azure OpenAI / Foundry-compatible chat endpoint
- Optional Tavily or Brave Search API key for web search support

## Configuration

The app loads settings from environment variables and an optional `.env` file.

Important settings include:

- `APP_NAME`
- `APP_ENV`
- `COSMOS_ENDPOINT`
- `COSMOS_KEY`
- `COSMOS_DATABASE_NAME`
- `COSMOS_SESSIONS_CONTAINER_NAME`
- `COSMOS_MESSAGES_CONTAINER_NAME`
- `COSMOS_VERIFY_SSL`
- `FOUNDRY_OPENAI_BASE_URL`
- `FOUNDRY_DEFAULT_CHAT_MODEL`
- `FOUNDRY_PREMIUM_CHAT_MODEL`
- `AZURE_OPENAI_VERIFY_SSL`
- `TAVILY_API_KEY` *(optional)*
- `BRAVE_SEARCH_API_KEY` *(optional)*
- `WEB_SEARCH_TIMEOUT_SECONDS`
- `WEB_SEARCH_MAX_RESULTS`

See `src/agent_86/core/config.py` for the full set of supported settings.

## Local Development

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the repository root and provide the required Cosmos DB and model settings.

Example:

```env
APP_NAME=agent-86
APP_ENV=dev

COSMOS_ENDPOINT=https://your-cosmos-account.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=agent86
COSMOS_SESSIONS_CONTAINER_NAME=sessions
COSMOS_MESSAGES_CONTAINER_NAME=messages

FOUNDRY_OPENAI_BASE_URL=https://your-foundry-or-openai-endpoint/
FOUNDRY_DEFAULT_CHAT_MODEL=gpt-4.1-mini
FOUNDRY_PREMIUM_CHAT_MODEL=gpt-5.4

TAVILY_API_KEY=
BRAVE_SEARCH_API_KEY=
```

### 3. Run the FastAPI backend

```bash
PYTHONPATH=src uvicorn agent_86.main:app --reload
```

### 4. Run the Streamlit development UI

In another terminal:

```bash
streamlit run dev_ui.py
```

### Optional: run the MCP stdio server

Install the optional MCP dependency without changing the core app requirements:

```bash
pip install -r requirements.txt -r requirements-mcp.txt
```

Then start the stdio MCP server from the repository root:

```bash
PYTHONPATH=src python -m agent_86.mcp.server
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
        "cd /Users/johnmanaloto/source/github/jqm-agent-86 && PYTHONPATH=src python -m agent_86.mcp.server"
      ]
    }
  }
}
```

If you use a virtual environment, replace `python` in the command with that environment's interpreter.

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

The chat endpoint currently:

- stores the incoming user message
- auto-titles default sessions from the prompt when appropriate
- selects a configured model tier
- optionally enables the web search tool
- stores tool transcript messages returned from the model workflow
- stores the final assistant message with model metadata

## Development UI

`dev_ui.py` is a Streamlit-based frontend that can:

- list existing sessions
- create, rename, and delete sessions
- view session history
- choose a model for chat requests
- enable optional web search
- send prompts to the backend chat endpoint

## Current Limitations

- Local development currently uses a hardcoded user identity (`local-dev-user`)
- Production authentication and authorization are not implemented yet
- The current tool set is minimal and focused on web search
- Web search only works when a provider key is configured and the request looks search-worthy
- Persistence depends on a reachable Cosmos DB endpoint and configured containers

## Roadmap

Near-term focus areas still include:

- stronger prompt construction and routing rules
- better observability and smoke tests
- additional tool integrations such as Azure inspection and GitHub access
- future file upload, artifact storage, and generated output workflows
- eventual Entra-based authentication and production hardening

## Additional Docs

- `docs/decisions.md`
- `docs/implementation-plan/roadmap.md`
- `scripts/cosmos_db/local_cosmosdb.zsh`

## Status

This repository now contains a working implementation of the initial backend slice. The current focus is improving documentation, extending tools, and evolving the app toward a more production-capable Azure-native agent platform.