from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest

SSE_COMPLETE_EVENT = "complete"
SSE_DELTA_EVENT = "delta"
SSE_DONE_EVENT = "done"
SSE_ERROR_EVENT = "error"
SSE_START_EVENT = "start"


def _resolved_user_id_from_access_token(access_token: str) -> str:
    claims = jwt.decode(
        access_token,
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_iss": False,
            "verify_exp": False,
        },
    )
    user_id = claims.get("oid") or claims.get("sub")
    assert user_id, "E2E access token is missing both oid and sub claims"
    return str(user_id)


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@pytest.fixture
def session_factory(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
):
    created_session_ids: list[str] = []

    def _create_session(
        *,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"metadata": metadata or {}}
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


def _parse_sse_events(response: httpx.Response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_event_name: str | None = None
    current_data_lines: list[str] = []

    for line in response.iter_lines():
        if line == "":
            if current_event_name is not None:
                payload_text = "\n".join(current_data_lines) if current_data_lines else "{}"
                events.append(
                    {
                        "event": current_event_name,
                        "data": json.loads(payload_text),
                    }
                )
            current_event_name = None
            current_data_lines = []
            continue

        if line.startswith("event: "):
            current_event_name = line.removeprefix("event: ")
            continue

        if line.startswith("data: "):
            current_data_lines.append(line.removeprefix("data: "))

    if current_event_name is not None:
        payload_text = "\n".join(current_data_lines) if current_data_lines else "{}"
        events.append(
            {
                "event": current_event_name,
                "data": json.loads(payload_text),
            }
        )

    return events


@pytest.mark.e2e
def test_chat_stream_returns_named_sse_events_and_persists_messages(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-chat-stream-session"),
        metadata={"case": "chat-stream", "nonce": _unique_label("chat-stream")},
    )
    expected_user_id = _resolved_user_id_from_access_token(
        e2e_authenticated_client.access_token
    )
    prompt = (
        "Reply with one short sentence about automated testing. "
        f"Nonce: {_unique_label('prompt')}"
    )
    request_metadata = {"client": "pytest-e2e", "mode": "stream"}

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
                "metadata": request_metadata,
                "tools": [],
            },
        ) as response:
            if response.status_code != 200:
                response.read()
            assert response.status_code == 200, response.text
            assert response.headers["content-type"].startswith("text/event-stream")
            events = _parse_sse_events(response)

    assert events, "Expected at least one SSE event"
    event_names = [event["event"] for event in events]
    assert event_names[0] == SSE_START_EVENT
    assert event_names[-1] == SSE_DONE_EVENT
    assert SSE_DELTA_EVENT in event_names
    assert event_names.count(SSE_COMPLETE_EVENT) == 1
    assert SSE_ERROR_EVENT not in event_names

    start_event = events[0]
    complete_event = next(event for event in events if event["event"] == SSE_COMPLETE_EVENT)
    delta_events = [event for event in events if event["event"] == SSE_DELTA_EVENT]

    assert start_event["data"] == {
        "session_id": created_session["id"],
        "model": start_event["data"]["model"],
        "tools": [],
    }
    assert isinstance(start_event["data"]["model"], str)
    assert start_event["data"]["model"]

    assistant_text_from_deltas = "".join(event["data"]["text"] for event in delta_events)
    assert assistant_text_from_deltas
    assert complete_event["data"]["assistant_text"] == assistant_text_from_deltas

    assistant_message = complete_event["data"]["message"]
    assert assistant_message["id"]
    assert assistant_message["session_id"] == created_session["id"]
    assert assistant_message["user_id"] == expected_user_id
    assert assistant_message["role"] == "assistant"
    assert assistant_message["content"] == assistant_text_from_deltas
    assert assistant_message["metadata"] == {
        "source": "foundry",
        "model": start_event["data"]["model"],
        "tools": [],
    }

    messages_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}/messages",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert messages_response.status_code == 200, messages_response.text
    messages = messages_response.json()
    assert len(messages) >= 2

    user_message = messages[0]
    persisted_assistant_message = messages[-1]

    assert user_message["session_id"] == created_session["id"]
    assert user_message["user_id"] == expected_user_id
    assert user_message["role"] == "user"
    assert user_message["content"] == prompt
    assert user_message["metadata"] == request_metadata

    assert persisted_assistant_message == assistant_message