import requests
import streamlit as st
import json

API_BASE_URL = "http://127.0.0.1:8000"
MODEL_OPTIONS = [
    "gpt-4.1-mini-2",
    "gpt-5.4",
]


def list_sessions() -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/sessions", timeout=30)
    response.raise_for_status()
    return response.json()


def create_session(title: str | None) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/sessions",
        json={"title": title, "metadata": {"source": "streamlit"}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def rename_session(session_id: str, title: str) -> dict:
    response = requests.patch(
        f"{API_BASE_URL}/sessions/{session_id}",
        json={"title": title},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def delete_session(session_id: str) -> None:
    response = requests.delete(
        f"{API_BASE_URL}/sessions/{session_id}",
        timeout=30,
    )
    response.raise_for_status()


def list_messages(session_id: str) -> list[dict]:
    response = requests.get(
        f"{API_BASE_URL}/sessions/{session_id}/messages",
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_chat(session_id: str, content: str, model: str, enable_web_search: bool) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/sessions/{session_id}/chat",
        json={
            "content": content,
            "metadata": {
                "source": "streamlit",
                "model": model,
                "enable_web_search": enable_web_search,
            },
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def stream_chat(
    session_id: str,
    content: str,
    model: str,
    enable_web_search: bool,
):
    response = requests.post(
        f"{API_BASE_URL}/sessions/{session_id}/chat/stream",
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


def render_message_content(message: dict) -> None:
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


st.set_page_config(page_title="agent-86", layout="wide")
st.title("agent-86")

if "selected_session_id" not in st.session_state:
    st.session_state.selected_session_id = None

try:
    sessions = list_sessions()
except requests.RequestException as exc:
    st.error(f"Could not reach backend: {exc}")
    st.stop()

existing_session_ids = {session["id"] for session in sessions}

if st.session_state.selected_session_id not in existing_session_ids:
    st.session_state.selected_session_id = sessions[0]["id"] if sessions else None

session_id = st.session_state.selected_session_id
selected_session = next((s for s in sessions if s["id"] == session_id), None)

with st.sidebar:
    st.subheader("Sessions")

    selected_model = st.selectbox(
        "Model",
        MODEL_OPTIONS,
        index=0,
    )

    enable_web_search = st.checkbox(
        "Enable web search",
        value=False,
        help="Allow backend to use web search tools for eligible requests."
    )

    new_title = st.text_input("New session title")
    if st.button("Create session", use_container_width=True):
        try:
            created = create_session(new_title or None)
            st.session_state.selected_session_id = created["id"]
            st.rerun()
        except requests.RequestException as exc:
            st.error(f"Create session failed: {exc}")

    for session in sessions:
        label = session["title"] or session["id"]
        is_selected = session["id"] == st.session_state.selected_session_id
        button_label = f"• {label}" if is_selected else label

        if st.button(
            button_label,
            key=f"session_{session['id']}",
            use_container_width=True,
        ):
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

                if st.button(
                    "Save name",
                    key=f"save_name_{session_id}",
                    use_container_width=True,
                ):
                    try:
                        rename_session(session_id, rename_title)
                        st.rerun()
                    except requests.RequestException as exc:
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
                        delete_session(session_id)
                        st.session_state.selected_session_id = None
                        st.rerun()
                    except requests.RequestException as exc:
                        st.error(f"Delete failed: {exc}")

if not session_id or selected_session is None:
    st.info("Create or select a session.")
else:
    session_title = selected_session["title"] or session_id
    st.subheader(session_title)
    st.caption(f"Session ID: {session_id}")

    try:
        messages = list_messages(session_id)
    except requests.RequestException as exc:
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
                for event in stream_chat(session_id, prompt, selected_model, enable_web_search):
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
            except requests.RequestException as exc:
                st.error(f"Chat request failed: {exc}")