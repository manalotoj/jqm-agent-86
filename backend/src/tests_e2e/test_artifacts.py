from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pytest


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@pytest.fixture
def session_factory(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
):
    created_session_ids: list[str] = []

    def _create_session(*, title: str | None = None, metadata: dict | None = None) -> dict:
        payload = {"metadata": metadata or {}}
        if title is not None:
            payload["title"] = title

        response = e2e_http_client.post(
            f"{e2e_authenticated_client.base_url}/sessions",
            headers=e2e_authenticated_client.authorization_header,
            json=payload,
        )
        assert response.status_code == 201, response.text
        session = response.json()
        created_session_ids.append(session["id"])
        return session

    yield _create_session

    for session_id in reversed(created_session_ids):
        response = e2e_http_client.delete(
            f"{e2e_authenticated_client.base_url}/sessions/{session_id}",
            headers=e2e_authenticated_client.authorization_header,
        )
        assert response.status_code in {204, 404}, response.text


def _upload_artifact(
    *,
    session_id: str,
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
    metadata: dict | None = None,
) -> dict:
    response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{session_id}/artifacts/upload",
        headers=e2e_authenticated_client.authorization_header,
        files={"file": (filename, content, content_type)},
        data={"metadata": json.dumps(metadata or {})},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.e2e
def test_artifact_upload_list_get_and_download(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-artifacts-session"),
        metadata={"case": "artifacts", "nonce": _unique_label("artifacts")},
    )
    artifact_content = f"artifact-content-{_unique_label('body')}".encode()
    artifact = _upload_artifact(
        session_id=created_session["id"],
        e2e_authenticated_client=e2e_authenticated_client,
        e2e_http_client=e2e_http_client,
        filename="artifact.txt",
        content=artifact_content,
        metadata={"label": "e2e-primary"},
    )

    assert artifact["session_id"] == created_session["id"]
    assert artifact["filename"] == "artifact.txt"
    assert artifact["content_type"] == "text/plain"
    assert artifact["size_bytes"] == len(artifact_content)
    assert artifact["metadata"] == {"label": "e2e-primary"}

    list_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert list_response.status_code == 200, list_response.text
    listed = list_response.json()
    assert [item["id"] for item in listed] == [artifact["id"]]

    get_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts/{artifact['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json() == artifact

    download_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts/{artifact['id']}/download",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == artifact_content
    assert download_response.headers["content-type"].startswith("text/plain")
    assert "attachment;" in download_response.headers["content-disposition"].lower()


@pytest.mark.e2e
def test_chat_stream_accepts_artifact_ids_and_persists_user_message_metadata(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-chat-artifacts-session"),
        metadata={"case": "chat-artifacts", "nonce": _unique_label("chat-artifacts")},
    )
    artifact = _upload_artifact(
        session_id=created_session["id"],
        e2e_authenticated_client=e2e_authenticated_client,
        e2e_http_client=e2e_http_client,
        filename="context.txt",
        content=b"artifact context",
    )
    prompt = f"Reply briefly about attachments. Nonce: {_unique_label('chat')}"

    with httpx.Client(timeout=60.0, follow_redirects=True) as streaming_client:
        with streaming_client.stream(
            "POST",
            f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/chat/stream",
            headers={
                **e2e_authenticated_client.authorization_header,
                "Accept": "text/event-stream",
            },
            json={
                "content": prompt,
                "metadata": {"artifact_ids": [artifact["id"], artifact["id"]]},
                "tools": [],
            },
        ) as response:
            if response.status_code != 200:
                response.read()
            assert response.status_code == 200, response.text
            response.read()

    messages_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/messages",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert messages_response.status_code == 200, messages_response.text
    messages = messages_response.json()
    user_messages = [message for message in messages if message["role"] == "user"]
    assert user_messages
    assert user_messages[-1]["content"] == prompt
    assert user_messages[-1]["metadata"] == {"artifact_ids": [artifact["id"]]}


@pytest.mark.e2e
def test_generated_artifact_create_list_get_and_download_with_lineage(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-generated-artifacts-session"),
        metadata={"case": "generated-artifacts", "nonce": _unique_label("generated-artifacts")},
    )
    source_artifact = _upload_artifact(
        session_id=created_session["id"],
        e2e_authenticated_client=e2e_authenticated_client,
        e2e_http_client=e2e_http_client,
        filename="source.txt",
        content=b"source artifact",
        metadata={"label": "source"},
    )

    message_response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/messages",
        headers=e2e_authenticated_client.authorization_header,
        json={"role": "assistant", "content": "Generated a revision", "metadata": {}},
    )
    assert message_response.status_code == 201, message_response.text
    assistant_message = message_response.json()

    generated_content = b"generated artifact body"
    create_response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts/generated",
        headers=e2e_authenticated_client.authorization_header,
        json={
            "filename": "source-revised.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(generated_content).decode("ascii"),
            "source_artifact_ids": [source_artifact["id"], source_artifact["id"]],
            "generated_by_message_id": assistant_message["id"],
            "metadata": {"label": "generated"},
        },
    )
    assert create_response.status_code == 201, create_response.text
    generated_artifact = create_response.json()
    assert generated_artifact["session_id"] == created_session["id"]
    assert generated_artifact["filename"] == "source-revised.txt"
    assert generated_artifact["content_type"] == "text/plain"
    assert generated_artifact["size_bytes"] == len(generated_content)
    assert generated_artifact["metadata"] == {
        "label": "generated",
        "artifact_kind": "generated",
        "source_artifact_ids": [source_artifact["id"]],
        "generated_by_message_id": assistant_message["id"],
    }

    list_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert list_response.status_code == 200, list_response.text
    listed = list_response.json()
    assert [item["id"] for item in listed] == [source_artifact["id"], generated_artifact["id"]]

    get_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts/{generated_artifact['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["metadata"] == generated_artifact["metadata"]

    download_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts/{generated_artifact['id']}/download",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert download_response.status_code == 200, download_response.text
    assert download_response.content == generated_content
    assert download_response.headers["content-type"].startswith("text/plain")

    missing_message_response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/artifacts/generated",
        headers=e2e_authenticated_client.authorization_header,
        json={
            "filename": "missing-message.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"invalid lineage").decode("ascii"),
            "source_artifact_ids": [source_artifact["id"]],
            "generated_by_message_id": "missing-message",
            "metadata": {},
        },
    )
    assert missing_message_response.status_code == 404, missing_message_response.text


@pytest.mark.e2e
def test_generated_artifact_rejects_source_from_wrong_session(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    first_session = session_factory(title=_unique_label("e2e-generated-owning-session"))
    second_session = session_factory(title=_unique_label("e2e-generated-other-session"))
    source_artifact = _upload_artifact(
        session_id=first_session["id"],
        e2e_authenticated_client=e2e_authenticated_client,
        e2e_http_client=e2e_http_client,
        filename="wrong-session-source.txt",
        content=b"session scoped",
    )

    create_response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{second_session['id']}/artifacts/generated",
        headers=e2e_authenticated_client.authorization_header,
        json={
            "filename": "should-not-work.txt",
            "content_type": "text/plain",
            "content_base64": base64.b64encode(b"bad lineage").decode("ascii"),
            "source_artifact_ids": [source_artifact["id"]],
            "metadata": {},
        },
    )

    assert create_response.status_code == 404, create_response.text


@pytest.mark.e2e
def test_chat_with_large_attached_artifact_preserves_only_user_and_assistant_messages(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-artifact-chat-context"),
        metadata={"case": "artifact-chat-context", "nonce": _unique_label("artifact-chat")},
    )
    large_artifact = _upload_artifact(
        session_id=created_session["id"],
        e2e_authenticated_client=e2e_authenticated_client,
        e2e_http_client=e2e_http_client,
        filename="large-context.txt",
        content=(b"A" * 25000),
        metadata={"label": "large-context"},
    )

    chat_response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/chat",
        headers=e2e_authenticated_client.authorization_header,
        json={
            "content": (
                "Use the attached file. If you cannot see the whole attachment, say clearly that only part of it was visible. "
                "Repeat the exact phrase PARTIAL-ATTACHMENT-DISCLOSURE in your answer."
            ),
            "metadata": {"artifact_ids": [large_artifact["id"]]},
            "tools": [],
        },
    )
    assert chat_response.status_code == 201, chat_response.text

    response_payload = chat_response.json()
    assistant_message = response_payload["message"]
    assert "PARTIAL-ATTACHMENT-DISCLOSURE" in assistant_message["content"]

    messages_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/messages",
        headers=e2e_authenticated_client.authorization_header,
    )
    assert messages_response.status_code == 200, messages_response.text
    persisted_messages = messages_response.json()
    assert len(persisted_messages) >= 2
    assert persisted_messages[-2]["role"] == "user"
    assert persisted_messages[-2]["metadata"]["artifact_ids"] == [large_artifact["id"]]
    assert persisted_messages[-1]["role"] == "assistant"
    assert persisted_messages[-1]["content"] == assistant_message["content"]
    assert all(message["metadata"].get("message_type") != "artifact_context" for message in persisted_messages)


@pytest.mark.e2e
def test_artifact_access_rejects_wrong_session(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    first_session = session_factory(title=_unique_label("e2e-artifacts-owning-session"))
    second_session = session_factory(title=_unique_label("e2e-artifacts-other-session"))
    artifact = _upload_artifact(
        session_id=first_session["id"],
        e2e_authenticated_client=e2e_authenticated_client,
        e2e_http_client=e2e_http_client,
        filename="wrong-session.txt",
        content=b"session scoped",
    )

    get_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{second_session['id']}/artifacts/{artifact['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )
    chat_response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{second_session['id']}/chat",
        headers=e2e_authenticated_client.authorization_header,
        json={
            "content": "Use wrong session artifact",
            "metadata": {"artifact_ids": [artifact["id"]]},
            "tools": [],
        },
    )

    assert get_response.status_code == 404, get_response.text
    assert chat_response.status_code == 404, chat_response.text