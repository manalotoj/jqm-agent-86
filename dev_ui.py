import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"


def list_sessions() -> list[dict]:
    response = requests.get(f"{API_BASE_URL}/sessions", timeout=30)
    response.raise_for_status()
    return response.json()


def create_session(title: str) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/sessions",
        json={"title": title, "metadata": {"source": "streamlit"}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_messages(session_id: str) -> list[dict]:
    response = requests.get(
        f"{API_BASE_URL}/sessions/{session_id}/messages",
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def send_chat(session_id: str, content: str) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/sessions/{session_id}/chat",
        json={"content": content, "metadata": {"source": "streamlit"}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="agent-86", layout="wide")
st.title("agent-86")

if "selected_session_id" not in st.session_state:
    st.session_state.selected_session_id = None

with st.sidebar:
    st.subheader("Sessions")

    new_title = st.text_input("New session title", value="")
    if st.button("Create session"):
        created = create_session(new_title or "Untitled session")
        st.session_state.selected_session_id = created["id"]
        st.rerun()

    sessions = list_sessions()

    for session in sessions:
        label = session["title"] or session["id"]
        if st.button(label, key=session["id"], use_container_width=True):
            st.session_state.selected_session_id = session["id"]
            st.rerun()

session_id = st.session_state.selected_session_id

if not session_id:
    st.info("Create or select a session.")
else:
    st.subheader(f"Session: {session_id}")

    messages = list_messages(session_id)

    for message in messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    prompt = st.chat_input("Send a message")
    if prompt:
        send_chat(session_id, prompt)
        st.rerun()