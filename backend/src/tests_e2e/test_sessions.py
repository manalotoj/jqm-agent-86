from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import httpx
import jwt
import pytest


def _parse_iso8601_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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


def _assert_session_shape(session: dict[str, Any]) -> None:
    assert session["id"]
    assert isinstance(session["metadata"], dict)
    created_at = _parse_iso8601_timestamp(session["created_at"])
    updated_at = _parse_iso8601_timestamp(session["updated_at"])
    assert updated_at >= created_at


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


@pytest.mark.e2e
def test_create_session_returns_created_session(
    e2e_authenticated_client,
    session_factory,
) -> None:
    session = session_factory(metadata={"case": "create", "nonce": _unique_label("create")})
    expected_user_id = _resolved_user_id_from_access_token(
        e2e_authenticated_client.access_token
    )

    _assert_session_shape(session)
    assert session["user_id"] == expected_user_id
    assert session["title"].startswith("New session ")


@pytest.mark.e2e
def test_list_sessions_includes_created_session(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-list-session"),
        metadata={"case": "list", "nonce": _unique_label("list")},
    )

    response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert response.status_code == 200, response.text
    sessions = response.json()
    assert any(session["id"] == created_session["id"] for session in sessions)


@pytest.mark.e2e
def test_get_single_session_returns_created_session(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-get-session"),
        metadata={"case": "get", "nonce": _unique_label("get")},
    )

    response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert response.status_code == 200, response.text
    fetched_session = response.json()
    _assert_session_shape(fetched_session)
    assert fetched_session == created_session


@pytest.mark.e2e
def test_update_session_persists_renamed_title(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-update-session"),
        metadata={"case": "update", "nonce": _unique_label("update")},
    )
    renamed_title = _unique_label("e2e-renamed-session")

    patch_response = e2e_http_client.patch(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}",
        headers=e2e_authenticated_client.authorization_header,
        json={"title": renamed_title},
    )

    assert patch_response.status_code == 200, patch_response.text
    patched_session = patch_response.json()
    assert patched_session["id"] == created_session["id"]
    assert patched_session["title"] == renamed_title

    get_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert get_response.status_code == 200, get_response.text
    fetched_session = get_response.json()
    _assert_session_shape(fetched_session)
    assert fetched_session["title"] == renamed_title
    assert fetched_session["id"] == created_session["id"]
    assert fetched_session["user_id"] == created_session["user_id"]
    assert fetched_session["metadata"] == created_session["metadata"]
    assert _parse_iso8601_timestamp(fetched_session["updated_at"]) >= _parse_iso8601_timestamp(
        created_session["updated_at"]
    )


@pytest.mark.e2e
def test_delete_session_returns_404_on_follow_up_get(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    session_factory,
) -> None:
    created_session = session_factory(
        title=_unique_label("e2e-delete-session"),
        metadata={"case": "delete", "nonce": _unique_label("delete")},
    )

    delete_response = e2e_http_client.delete(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert delete_response.status_code == 204, delete_response.text

    get_response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{created_session['id']}",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert get_response.status_code == 404, get_response.text
    assert get_response.json()["detail"] == f"Session '{created_session['id']}' not found"