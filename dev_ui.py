from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

import requests
import streamlit as st
from msal import ConfidentialClientApplication, SerializableTokenCache

MODEL_OPTIONS = [
    "gpt-4.1-mini-2",
    "gpt-5.4",
]
TOKEN_REFRESH_WINDOW_SECONDS = 300
AUTH_FLOW_SESSION_KEY = "entra_auth_flow"
MSAL_CLIENT_SESSION_KEY = "entra_msal_client"
MSAL_CACHE_SESSION_KEY = "entra_msal_cache"
MSAL_ACCOUNT_SESSION_KEY = "entra_msal_account"
API_SESSION_KEY = "agent_86_api_session"


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
    def api_scope(self) -> str:
        return f"{self.api_audience}/access_as_user"

    @property
    def login_scopes(self) -> list[str]:
        return ["openid", "profile", "offline_access", self.api_scope]


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


def _get_token_cache() -> SerializableTokenCache:
    cache = st.session_state.get(MSAL_CACHE_SESSION_KEY)
    if cache is None:
        cache = SerializableTokenCache()
        st.session_state[MSAL_CACHE_SESSION_KEY] = cache
    return cache


def get_msal_client(settings: UiAuthSettings) -> ConfidentialClientApplication:
    client = st.session_state.get(MSAL_CLIENT_SESSION_KEY)
    client_key = st.session_state.get(f"{MSAL_CLIENT_SESSION_KEY}_key")
    expected_key = (settings.authority, settings.ui_client_id, settings.redirect_uri)

    if client is None or client_key != expected_key:
        client = ConfidentialClientApplication(
            client_id=settings.ui_client_id,
            client_credential=settings.ui_client_secret,
            authority=settings.authority,
            token_cache=_get_token_cache(),
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


def _clear_auth_query_params() -> None:
    st.query_params.clear()


def begin_login(settings: UiAuthSettings, client: ConfidentialClientApplication) -> str:
    flow = client.initiate_auth_code_flow(
        scopes=settings.login_scopes,
        redirect_uri=settings.redirect_uri,
        response_mode="query",
    )
    st.session_state[AUTH_FLOW_SESSION_KEY] = flow
    return flow["auth_uri"]


def complete_login_if_callback(client: ConfidentialClientApplication) -> bool:
    auth_response = {
        key: value
        for key, value in st.query_params.to_dict().items()
        if value is not None
    }

    if not ({"code", "error", "state"} & set(auth_response)):
        return False

    flow = st.session_state.get(AUTH_FLOW_SESSION_KEY)
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

    _clear_auth_query_params()

    if "error" in result:
        description = result.get("error_description") or result["error"]
        raise RuntimeError(f"Microsoft Entra sign-in failed: {description}")

    claims = result.get("id_token_claims")
    preferred_username = claims.get("preferred_username") if isinstance(claims, Mapping) else None
    accounts = client.get_accounts(username=preferred_username) if preferred_username else client.get_accounts()
    if not accounts:
        raise RuntimeError("Microsoft Entra sign-in succeeded, but no cached account was found.")

    st.session_state[MSAL_ACCOUNT_SESSION_KEY] = accounts[0]
    return True


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
    st.markdown(
        f'<meta http-equiv="refresh" content="0; url={auth_uri}">',
        unsafe_allow_html=True,
    )
    st.link_button("Continue to Microsoft Entra ID", auth_uri, use_container_width=True)


def _ensure_authenticated(settings: UiAuthSettings) -> None:
    client = get_msal_client(settings)

    if complete_login_if_callback(client):
        st.rerun()

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
    for key in [
        AUTH_FLOW_SESSION_KEY,
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