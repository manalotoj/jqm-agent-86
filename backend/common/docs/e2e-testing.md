# E2E testing

This directory contains the scaffolding for true end-to-end backend tests.
Unlike the existing mocked tests in `backend/src/tests/`, these tests:

- talk to a **real running server**
- acquire a **real Entra access token** using the client credentials grant
- hit the server over real HTTP
- assume the server is already running in `AGENT86_ENV_MODE=e2e`

## 1. Server-side config: `backend/.env.e2e`

`common/scripts/start_local.zsh` already supports `AGENT86_ENV_MODE=e2e` and will load:

1. `backend/.env.common`
2. `backend/.env.api`
3. `backend/.env.e2e`

The last file wins, so `backend/.env.e2e` should override any values that must differ for e2e.

Create `backend/.env.e2e` manually. Do **not** commit it. At minimum it should contain the real server-side settings needed by the app, including:

```dotenv
# REQUIRED: must point at a completely separate Cosmos account used only for e2e.
# Per project decision, the account hostname should include `e2e` or `test`.
COSMOS_ENDPOINT=https://your-e2e-or-test-account.documents.azure.com:443/
COSMOS_KEY=replace-with-real-key
COSMOS_DATABASE_NAME=your-e2e-database-name

# Plus the rest of the backend settings required by the app in this environment,
# for example the Entra and Foundry values already used by the server:
ENTRA_TENANT_ID=...
ENTRA_API_CLIENT_ID=...
ENTRA_API_AUDIENCE=...
FOUNDRY_OPENAI_BASE_URL=...
FOUNDRY_OPENAI_API_KEY=...
FOUNDRY_DEFAULT_CHAT_MODEL=...
FOUNDRY_PREMIUM_CHAT_MODEL=...
```

Note: `COSMOS_DATABASE_NAME` is still a required backend setting with `Field(min_length=3)` and no default in `backend/src/agent_86/core/config.py`.

## 2. Test-client config: `backend/.env.e2e.client`

This file is read by pytest only. It is intentionally separate from the server config above.

Copy the example file and fill in real values:

```bash
cp /Users/johnmanaloto/source/github/jqm-agent-86/backend/.env.e2e.client.example \
   /Users/johnmanaloto/source/github/jqm-agent-86/backend/.env.e2e.client
```

Expected keys:

```dotenv
E2E_API_BASE_URL=http://127.0.0.1:8000
E2E_ENTRA_TENANT_ID=...
E2E_ENTRA_CLIENT_ID=...
E2E_ENTRA_CLIENT_SECRET=...
E2E_ENTRA_API_AUDIENCE=api://...
```

## 3. Start the server in e2e mode

From the repo root:

```bash
AGENT86_ENV_MODE=e2e ./common/scripts/start_local.zsh
```

The e2e suite does **not** start the server for you. It fails fast if `/health` is unreachable.

## 4. Run the suite

Default pytest runs exclude the `e2e` marker on purpose. To run this suite explicitly, from the repo root use:

```bash
PYTHONPATH=/Users/johnmanaloto/source/github/jqm-agent-86/backend/src \
/Users/johnmanaloto/source/github/jqm-agent-86/backend/.venv/bin/pytest \
backend/src/tests_e2e -m e2e
```

To run only the smoke harness tests:

```bash
PYTHONPATH=/Users/johnmanaloto/source/github/jqm-agent-86/backend/src \
/Users/johnmanaloto/source/github/jqm-agent-86/backend/.venv/bin/pytest \
backend/src/tests_e2e/test_smoke.py -m e2e
```

## What the smoke tests prove

- `test_health_endpoint_is_reachable` proves the configured server is reachable over real HTTP
- `test_authenticated_sessions_list_returns_200` proves:
  - client credentials token acquisition works
  - the bearer token is accepted by the backend
  - the backend's Entra validation path is working end to end

## Dependencies

No additional e2e-only Python packages were needed for this scaffold, because `httpx`, `msal`, and `pydantic-settings` are already present in `backend/requirements.txt`.
