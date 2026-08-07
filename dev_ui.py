from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests
import streamlit as st
from msal import ConfidentialClientApplication, SerializableTokenCache

MODEL_OPTIONS = [
    "gpt-4.1-mini-2",
    "gpt-5.4",
]
TOKEN_REFRESH_WINDOW_SECONDS = 300
AUTH_FLOW_SESSION_KEY = "entra_auth_flow"
AUTH_SESSION_ID_SESSION_KEY = "entra_auth_session_id"
MSAL_CLIENT_SESSION_KEY = "entra_msal_client"
MSAL_CACHE_SESSION_KEY = "entra_msal_cache"
MSAL_ACCOUNT_SESSION_KEY = "entra_msal_account"
API_SESSION_KEY = "agent_86_api_session"
AUTH_SESSION_QUERY_PARAM = "auth_session"
PENDING_AUTH_FLOW_TTL_SECONDS = 600
PERSISTED_AUTH_SESSION_TTL_SECONDS = 43200


@dataclass
class PendingAuthFlow:
    flow: dict[str, Any]
    settings_key: tuple[str, str, str]
    created_at: float


@dataclass
class PersistedAuthSession:
    account: Mapping[str, Any]
    token_cache: str
    settings_key: tuple[str, str, str]
    created_at: float


# These MUST be st.cache_resource-backed rather than plain module-level
# dicts. Streamlit re-executes this entire file top-to-bottom on every
# rerun (every browser connection, every st.rerun(), every widget
# interaction) -- a bare `= {}` assignment would silently wipe these on
# the very next run, which is exactly what was breaking the OAuth
# callback handoff. st.cache_resource caches the *return value* once and
# hands back the same object on every subsequent call, across reruns and
# across sessions, for the lifetime of the process.
@st.cache_resource
def _pending_auth_flows() -> dict[str, PendingAuthFlow]:
    return {}


@st.cache_resource
def _persisted_auth_sessions() -> dict[str, PersistedAuthSession]:
    return {}


@dataclass(frozen=True)
class UiAuthSettings:
    tenant_id: str
    ui_client_id: str
    ui_client_secret: str
    redirect_uri: str
    api_audience: str
    api_base_url: str = "http://127.0.0.1:8000"

    @property
    def authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.tenant_id}"

    @property
    def app_base_url(self) -> str:
        # redirect_uri is expected to point at a path Streamlit actually
        # serves -- in practice this means the app root ("/"). Streamlit
        # only routes requests it knows about (root, its own static/
        # websocket routes, and registered multipage-app page slugs);
        # anything else 404s before your script ever runs. Do not point
        # this at a made-up path like /oauth2callback or /auth/callback.
        parsed = urlsplit(self.redirect_uri)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))

    @property
    def api_scope(self) -> str:
        return f"{self.api_audience}/access_as_user"

    @property
    def login_scopes(self) -> list[str]:
        return [self.api_scope]


def load_ui_settings(env: Mapping[str, str] | None = None) -> UiAuthSettings:
    env = env or os.environ

    missing: list[str] = []

    def required(name: str) -> str:
        value = (env.get(name) or "").strip()
        if not value:
            missing.append(name)
        return value

    tenant_id = required("ENTRA_TENANT_ID")
    ui_client_id = required("ENTRA_UI_CLIENT_ID")
    ui_client_secret = required("ENTRA_UI_CLIENT_SECRET")
    redirect_uri = required("ENTRA_REDIRECT_URI")

    api_audience = (env.get("ENTRA_API_AUDIENCE") or "").strip()
    if not api_audience:
        backend_client_id = (env.get("ENTRA_API_CLIENT_ID") or "").strip()
        if backend_client_id:
            api_audience = f"api://{backend_client_id}"
        else:
            missing.append("ENTRA_API_AUDIENCE or ENTRA_API_CLIENT_ID")

    if missing:
        joined = ", ".join(sorted(set(missing)))
        raise ValueError(f"Missing required UI authentication configuration: {joined}")

    api_base_url = (env.get("API_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")

    return UiAuthSettings(
        tenant_id=tenant_id,
        ui_client_id=ui_client_id,
        ui_client_secret=ui_client_secret,
        redirect_uri=redirect_uri,
        api_audience=api_audience,
        api_base_url=api_base_url,
    )


def _expires_soon(
    token_result: Mapping[str, Any],
    threshold_seconds: int = TOKEN_REFRESH_WINDOW_SECONDS,
    now: Callable[[], float] = time.time,
) -> bool:
    expires_on = token_result.get("expires_on")
    if expires_on is None:
        return False

    try:
        return int(expires_on) - int(now()) <= threshold_seconds
    except (TypeError, ValueError):
        return False


def _settings_key(settings: UiAuthSettings) -> tuple[str, str, str]:
    return (settings.authority, settings.ui_client_id, settings.redirect_uri)


def _prune_expired_auth_state(now: Callable[[], float] = time.time) -> None:
    current_time = now()

    pending_flows = _pending_auth_flows()
    for state, pending in list(pending_flows.items()):
        if current_time - pending.created_at > PENDING_AUTH_FLOW_TTL_SECONDS:
            del pending_flows[state]

    persisted_sessions = _persisted_auth_sessions()
    for session_id, persisted in list(persisted_sessions.items()):
        if current_time - persisted.created_at > PERSISTED_AUTH_SESSION_TTL_SECONDS:
            del persisted_sessions[session_id]


def _current_query_params() -> dict[str, str]:
    return {
        key: value
        for key, value in st.query_params.to_dict().items()
        if value is not None
    }


def _set_query_params(params: Mapping[str, str]) -> None:
    st.query_params.clear()
    for key, value in params.items():
        st.query_params[key] = value


def _auth_session_id_from_query_params() -> str | None:
    value = _current_query_params().get(AUTH_SESSION_QUERY_PARAM)
    if value:
        return str(value)
    return None


def _clear_auth_query_params(*, preserve_auth_session: bool = False) -> None:
    params = _current_query_params()
    for key in ["code", "state", "session_state", "error", "error_description"]:
        params.pop(key, None)

    if not preserve_auth_session:
        params.pop(AUTH_SESSION_QUERY_PARAM, None)

    _set_query_params(params)


def _build_url_with_query(base_url: str, params: Mapping[str, str]) -> str:
    parsed = urlsplit(base_url)
    merged_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    merged_params.update(params)
    query = urlencode(merged_params)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", query, parsed.fragment))


def _build_post_auth_redirect_url(settings: UiAuthSettings, auth_session_id: str) -> str:
    return _build_url_with_query(
        settings.app_base_url,
        {AUTH_SESSION_QUERY_PARAM: auth_session_id},
    )


def _restore_persisted_auth_session(settings: UiAuthSettings) -> None:
    _prune_expired_auth_state()

    auth_session_id = _auth_session_id_from_query_params()
    if not auth_session_id:
        return

    persisted = _persisted_auth_sessions().get(auth_session_id)
    if persisted is None or persisted.settings_key != _settings_key(settings):
        return

    cache = st.session_state.get(MSAL_CACHE_SESSION_KEY)
    if cache is None:
        cache = SerializableTokenCache()
        if persisted.token_cache:
            cache.deserialize(persisted.token_cache)
        st.session_state[MSAL_CACHE_SESSION_KEY] = cache

    if not st.session_state.get(MSAL_ACCOUNT_SESSION_KEY):
        st.session_state[MSAL_ACCOUNT_SESSION_KEY] = dict(persisted.account)

    st.session_state[AUTH_SESSION_ID_SESSION_KEY] = auth_session_id


def _get_token_cache(settings: UiAuthSettings) -> SerializableTokenCache:
    _restore_persisted_auth_session(settings)
    cache = st.session_state.get(MSAL_CACHE_SESSION_KEY)
    if cache is None:
        cache = SerializableTokenCache()
        st.session_state[MSAL_CACHE_SESSION_KEY] = cache
    return cache


def _persist_auth_session(
    settings: UiAuthSettings,
    account: Mapping[str, Any],
    *,
    auth_session_id: str | None = None,
) -> str:
    _prune_expired_auth_state()

    session_id = (
        auth_session_id
        or st.session_state.get(AUTH_SESSION_ID_SESSION_KEY)
        or _auth_session_id_from_query_params()
        or uuid.uuid4().hex
    )

    _persisted_auth_sessions()[str(session_id)] = PersistedAuthSession(
        account=dict(account),
        token_cache=_get_token_cache(settings).serialize(),
        settings_key=_settings_key(settings),
        created_at=time.time(),
    )
    st.session_state[AUTH_SESSION_ID_SESSION_KEY] = str(session_id)
    return str(session_id)


def get_msal_client(settings: UiAuthSettings) -> ConfidentialClientApplication:
    _restore_persisted_auth_session(settings)
    client = st.session_state.get(MSAL_CLIENT_SESSION_KEY)
    client_key = st.session_state.get(f"{MSAL_CLIENT_SESSION_KEY}_key")
    expected_key = _settings_key(settings)

    if client is None or client_key != expected_key:
        client = ConfidentialClientApplication(
            client_id=settings.ui_client_id,
            client_credential=settings.ui_client_secret,
            authority=settings.authority,
            token_cache=_get_token_cache(settings),
        )
        st.session_state[MSAL_CLIENT_SESSION_KEY] = client
        st.session_state[f"{MSAL_CLIENT_SESSION_KEY}_key"] = expected_key

    return client


def _get_account(client: ConfidentialClientApplication) -> Mapping[str, Any] | None:
    account = st.session_state.get(MSAL_ACCOUNT_SESSION_KEY)
    if account:
        return account

    accounts = client.get_accounts()
    if accounts:
        account = accounts[0]
        st.session_state[MSAL_ACCOUNT_SESSION_KEY] = account
        return account

    return None


def begin_login(settings: UiAuthSettings, client: ConfidentialClientApplication) -> str:
    _prune_expired_auth_state()
    flow = client.initiate_auth_code_flow(
        scopes=settings.login_scopes,
        redirect_uri=settings.redirect_uri,
        response_mode="query",
    )
    st.session_state[AUTH_FLOW_SESSION_KEY] = flow
    state = flow.get("state")
    if state:
        _pending_auth_flows()[str(state)] = PendingAuthFlow(
            flow=flow,
            settings_key=_settings_key(settings),
            created_at=time.time(),
        )
    return flow["auth_uri"]


def complete_login_if_callback(
    settings: UiAuthSettings,
    client: ConfidentialClientApplication,
) -> str | None:
    auth_response = _current_query_params()

    if not ({"code", "error", "state"} & set(auth_response)):
        return None

    flow = st.session_state.get(AUTH_FLOW_SESSION_KEY)
    state = auth_response.get("state")
    if flow is None and state:
        pending_flow = _pending_auth_flows().get(str(state))
        if pending_flow and pending_flow.settings_key == _settings_key(settings):
            flow = pending_flow.flow

    if not flow:
        _clear_auth_query_params()
        raise RuntimeError("Authentication callback received without a matching sign-in session.")

    try:
        result = client.acquire_token_by_auth_code_flow(flow, auth_response)
    except ValueError as exc:
        _clear_auth_query_params()
        raise RuntimeError("Authentication callback validation failed.") from exc
    finally:
        st.session_state.pop(AUTH_FLOW_SESSION_KEY, None)
        if state:
            _pending_auth_flows().pop(str(state), None)

    if "error" in result:
        _clear_auth_query_params()
        description = result.get("error_description") or result["error"]
        raise RuntimeError(f"Microsoft Entra sign-in failed: {description}")

    claims = result.get("id_token_claims")
    preferred_username = claims.get("preferred_username") if isinstance(claims, Mapping) else None
    accounts = client.get_accounts(username=preferred_username) if preferred_username else client.get_accounts()
    if not accounts:
        _clear_auth_query_params()
        raise RuntimeError("Microsoft Entra sign-in succeeded, but no cached account was found.")

    st.session_state[MSAL_ACCOUNT_SESSION_KEY] = accounts[0]
    auth_session_id = _persist_auth_session(
        settings,
        accounts[0],
        auth_session_id=uuid.uuid4().hex,
    )
    _clear_auth_query_params(preserve_auth_session=False)
    return _build_post_auth_redirect_url(settings, auth_session_id)


def get_access_token(
    settings: UiAuthSettings,
    client: ConfidentialClientApplication,
    *,
    force_refresh: bool = False,
) -> str | None:
    account = _get_account(client)
    if account is None:
        return None

    result = client.acquire_token_silent_with_error(
        scopes=[settings.api_scope],
        account=account,
        force_refresh=force_refresh,
    )

    if not result:
        return None

    if "error" in result:
        description = result.get("error_description") or result["error"]
        raise RuntimeError(f"Failed to acquire API access token: {description}")

    if not force_refresh and _expires_soon(result):
        refreshed = client.acquire_token_silent_with_error(
            scopes=[settings.api_scope],
            account=account,
            force_refresh=True,
        )
        if refreshed and "access_token" in refreshed and "error" not in refreshed:
            result = refreshed

    _persist_auth_session(settings, account)

    return result.get("access_token")


def get_api_session() -> requests.Session:
    session = st.session_state.get(API_SESSION_KEY)
    if session is None:
        session = requests.Session()
        st.session_state[API_SESSION_KEY] = session
    return session


def perform_authenticated_request(
    session: requests.Session,
    method: str,
    url: str,
    token_provider: Callable[[bool], str],
    *,
    retry_on_401: bool = True,
    **kwargs: Any,
) -> requests.Response:
    headers = dict(kwargs.pop("headers", {}) or {})
    token = token_provider(False)
    headers["Authorization"] = f"Bearer {token}"

    response = session.request(method, url, headers=headers, **kwargs)
    if response.status_code != 401 or not retry_on_401:
        return response

    response.close()
    refreshed_token = token_provider(True)
    retry_headers = dict(headers)
    retry_headers["Authorization"] = f"Bearer {refreshed_token}"
    return session.request(method, url, headers=retry_headers, **kwargs)


def api_request(
    settings: UiAuthSettings,
    method: str,
    path: str,
    *,
    retry_on_401: bool = True,
    **kwargs: Any,
) -> requests.Response:
    client = get_msal_client(settings)

    def token_provider(force_refresh: bool) -> str:
        token = get_access_token(settings, client, force_refresh=force_refresh)
        if not token:
            raise RuntimeError("User is not authenticated.")
        return token

    url = f"{settings.api_base_url}/{path.lstrip('/')}"
    return perform_authenticated_request(
        get_api_session(),
        method,
        url,
        token_provider,
        retry_on_401=retry_on_401,
        **kwargs,
    )


def list_sessions(settings: UiAuthSettings) -> list[dict[str, Any]]:
    response = api_request(settings, "GET", "/sessions", timeout=30)
    response.raise_for_status()
    return response.json()


def create_session(settings: UiAuthSettings, title: str | None) -> dict[str, Any]:
    response = api_request(
        settings,
        "POST",
        "/sessions",
        json={"title": title, "metadata": {"source": "streamlit"}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def rename_session(settings: UiAuthSettings, session_id: str, title: str) -> dict[str, Any]:
    response = api_request(
        settings,
        "PATCH",
        f"/sessions/{session_id}",
        json={"title": title},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def delete_session(settings: UiAuthSettings, session_id: str) -> None:
    response = api_request(settings, "DELETE", f"/sessions/{session_id}", timeout=30)
    response.raise_for_status()


def list_messages(settings: UiAuthSettings, session_id: str) -> list[dict[str, Any]]:
    response = api_request(settings, "GET", f"/sessions/{session_id}/messages", timeout=30)
    response.raise_for_status()
    return response.json()


def stream_chat(
    settings: UiAuthSettings,
    session_id: str,
    content: str,
    model: str,
    enable_web_search: bool,
):
    response = api_request(
        settings,
        "POST",
        f"/sessions/{session_id}/chat/stream",
        json={
            "content": content,
            "metadata": {
                "source": "streamlit",
                "model": model,
                "enable_web_search": enable_web_search,
            },
        },
        headers={"Accept": "text/event-stream"},
        timeout=300,
        stream=True,
    )
    response.raise_for_status()

    event_name = "message"
    data_lines: list[str] = []

    try:
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue

            line = raw_line.strip()
            if not line:
                if data_lines:
                    payload = "\n".join(data_lines)
                    yield {
                        "event": event_name,
                        "data": json.loads(payload) if payload else {},
                    }
                event_name = "message"
                data_lines = []
                continue

            if line.startswith("event:"):
                event_name = line.removeprefix("event:").strip()
            elif line.startswith("data:"):
                data_lines.append(line.removeprefix("data:").strip())

        if data_lines:
            payload = "\n".join(data_lines)
            yield {
                "event": event_name,
                "data": json.loads(payload) if payload else {},
            }
    finally:
        response.close()


def render_message_content(message: dict[str, Any]) -> None:
    metadata = message.get("metadata", {})
    message_type = metadata.get("message_type", "")

    if message_type == "function_call":
        tool_name = metadata.get("tool_name", "unknown_tool")
        arguments = metadata.get("arguments", "{}")
        st.caption(f"Tool called: {tool_name}")
        st.code(arguments, language="json")
        return

    if message_type == "function_call_output":
        st.markdown("**Tool output:**")
        st.write(message.get("content", ""))
        return

    st.write(message.get("content", ""))
    model_used = metadata.get("model")
    if model_used:
        st.caption(f"model: {model_used}")


def _render_sign_in_redirect(auth_uri: str) -> None:
    st.info("Redirecting to Microsoft Entra ID for sign-in…")
    escaped_auth_uri = json.dumps(auth_uri)
    st.html(
        f"""
        <script>
            window.location.replace({escaped_auth_uri});
        </script>
        """,
        unsafe_allow_javascript=True,
    )
    st.link_button("Continue to Microsoft Entra ID", auth_uri, use_container_width=True)


def _ensure_authenticated(settings: UiAuthSettings) -> None:
    client = get_msal_client(settings)

    post_auth_redirect_url = complete_login_if_callback(settings, client)
    if post_auth_redirect_url:
        _render_sign_in_redirect(post_auth_redirect_url)
        st.stop()

    if get_access_token(settings, client):
        return

    auth_uri = begin_login(settings, client)
    _render_sign_in_redirect(auth_uri)
    st.stop()


def _authenticated_username() -> str | None:
    account = st.session_state.get(MSAL_ACCOUNT_SESSION_KEY)
    if isinstance(account, Mapping):
        username = account.get("username")
        if username:
            return str(username)
    return None


def logout() -> None:
    auth_session_id = st.session_state.get(AUTH_SESSION_ID_SESSION_KEY) or _auth_session_id_from_query_params()
    if auth_session_id:
        _persisted_auth_sessions().pop(str(auth_session_id), None)

    for key in [
        AUTH_FLOW_SESSION_KEY,
        AUTH_SESSION_ID_SESSION_KEY,
        MSAL_CLIENT_SESSION_KEY,
        f"{MSAL_CLIENT_SESSION_KEY}_key",
        MSAL_CACHE_SESSION_KEY,
        MSAL_ACCOUNT_SESSION_KEY,
        API_SESSION_KEY,
    ]:
        st.session_state.pop(key, None)
    _clear_auth_query_params()


def main() -> None:
    st.set_page_config(page_title="agent-86", layout="wide")
    st.title("agent-86")

    try:
        settings = load_ui_settings()
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    try:
        _ensure_authenticated(settings)
    except RuntimeError as exc:
        st.error(str(exc))
        if st.button("Retry sign-in", use_container_width=True):
            logout()
            st.rerun()
        st.stop()

    if "selected_session_id" not in st.session_state:
        st.session_state.selected_session_id = None

    try:
        sessions = list_sessions(settings)
    except (requests.RequestException, RuntimeError) as exc:
        st.error(f"Could not reach backend: {exc}")
        st.stop()

    existing_session_ids = {session["id"] for session in sessions}

    if st.session_state.selected_session_id not in existing_session_ids:
        st.session_state.selected_session_id = sessions[0]["id"] if sessions else None

    session_id = st.session_state.selected_session_id
    selected_session = next((s for s in sessions if s["id"] == session_id), None)

    with st.sidebar:
        st.subheader("Sessions")

        signed_in_as = _authenticated_username()
        if signed_in_as:
            st.caption(f"Signed in as {signed_in_as}")

        if st.button("Sign out", use_container_width=True):
            logout()
            st.rerun()

        selected_model = st.selectbox("Model", MODEL_OPTIONS, index=0)
        enable_web_search = st.checkbox(
            "Enable web search",
            value=False,
            help="Allow backend to use web search tools for eligible requests.",
        )

        new_title = st.text_input("New session title")
        if st.button("Create session", use_container_width=True):
            try:
                created = create_session(settings, new_title or None)
                st.session_state.selected_session_id = created["id"]
                st.rerun()
            except (requests.RequestException, RuntimeError) as exc:
                st.error(f"Create session failed: {exc}")

        for session in sessions:
            label = session["title"] or session["id"]
            is_selected = session["id"] == st.session_state.selected_session_id
            button_label = f"• {label}" if is_selected else label

            if st.button(button_label, key=f"session_{session['id']}", use_container_width=True):
                st.session_state.selected_session_id = session["id"]
                st.rerun()

        if selected_session is not None:
            st.divider()
            col1, col2 = st.columns([5, 1])

            with col1:
                st.caption(f"Selected: {selected_session['title'] or selected_session['id']}")

            with col2:
                with st.popover("⋯", use_container_width=True):
                    st.markdown("**Manage session**")
                    rename_title = st.text_input(
                        "Rename session",
                        value=selected_session["title"] or "",
                        key=f"rename_{session_id}",
                    )

                    if st.button("Save name", key=f"save_name_{session_id}", use_container_width=True):
                        try:
                            rename_session(settings, session_id, rename_title)
                            st.rerun()
                        except (requests.RequestException, RuntimeError) as exc:
                            st.error(f"Rename failed: {exc}")

                    st.divider()
                    st.markdown("**Delete session**")
                    st.caption("This will delete the session and all messages.")
                    confirmed = st.checkbox(
                        "I understand this cannot be undone",
                        key=f"confirm_delete_checkbox_{session_id}",
                    )

                    if st.button(
                        "Delete session",
                        key=f"delete_session_{session_id}",
                        use_container_width=True,
                        type="primary",
                        disabled=not confirmed,
                    ):
                        try:
                            delete_session(settings, session_id)
                            st.session_state.selected_session_id = None
                            st.rerun()
                        except (requests.RequestException, RuntimeError) as exc:
                            st.error(f"Delete failed: {exc}")

    if not session_id or selected_session is None:
        st.info("Create or select a session.")
        return

    session_title = selected_session["title"] or session_id
    st.subheader(session_title)
    st.caption(f"Session ID: {session_id}")

    try:
        messages = list_messages(settings, session_id)
    except (requests.RequestException, RuntimeError) as exc:
        st.error(f"Could not load messages: {exc}")
        st.stop()

    for message in messages:
        with st.chat_message(message["role"]):
            render_message_content(message)

    prompt = st.chat_input("Send a message")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)

        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            tool_status_placeholder = st.empty()
            streamed_text = ""
            tool_events: list[str] = []

            try:
                for event in stream_chat(settings, session_id, prompt, selected_model, enable_web_search):
                    event_name = event.get("event", "message")
                    data = event.get("data", {})

                    if event_name == "delta":
                        streamed_text += data.get("text", "")
                        response_placeholder.markdown(streamed_text or "…")
                    elif event_name == "tool_call":
                        tool_name = data.get("tool_name", "unknown_tool")
                        tool_events.append(f"Calling tool: `{tool_name}`")
                        tool_status_placeholder.markdown("\n\n".join(tool_events))
                    elif event_name == "tool_result":
                        tool_name = data.get("tool_name", "unknown_tool")
                        content = data.get("content", "")
                        tool_events.append(f"Tool result from `{tool_name}`:\n\n{content}")
                        tool_status_placeholder.markdown("\n\n---\n\n".join(tool_events))
                    elif event_name == "error":
                        raise requests.RequestException(data.get("message", "Streaming request failed"))
                    elif event_name == "complete":
                        streamed_text = data.get("assistant_text", streamed_text)
                        response_placeholder.markdown(streamed_text or "*(empty response)*")

                st.rerun()
            except (requests.RequestException, RuntimeError) as exc:
                st.error(f"Chat request failed: {exc}")


if __name__ == "__main__":
    main()