from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import httpx
import pytest


def _unique_label(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@pytest.fixture
def artifact_analysis_session(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
):
    response = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions",
        headers=e2e_authenticated_client.authorization_header,
        json={"title": _unique_label("e2e-csv-analysis"), "metadata": {"e2e": "csv-analysis"}},
    )
    assert response.status_code == 201, response.text
    session = response.json()

    try:
        yield session
    finally:
        cleanup = e2e_http_client.delete(
            f"{e2e_authenticated_client.base_url}/sessions/{session['id']}",
            headers=e2e_authenticated_client.authorization_header,
        )
        assert cleanup.status_code in {204, 404}, cleanup.text


def _wait_for_terminal_analysis(
    *,
    base_url: str,
    headers: dict[str, str],
    session_id: str,
    artifact_id: str,
    job: dict[str, Any],
    client: httpx.Client,
) -> dict[str, Any]:
    deadline = time.monotonic() + 90
    while job["state"] in {"requested", "running"} and time.monotonic() < deadline:
        time.sleep(2)
        response = client.get(
            f"{base_url}/sessions/{session_id}/artifacts/{artifact_id}/analysis/{job['id']}",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        job = response.json()

    assert job["state"] not in {"requested", "running"}, job
    return job


@pytest.mark.e2e
def test_csv_artifact_analysis_reports_complete_coverage(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
    artifact_analysis_session: dict[str, Any],
) -> None:
    session_id = artifact_analysis_session["id"]
    headers = e2e_authenticated_client.authorization_header
    upload = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{session_id}/artifacts/upload",
        headers=headers,
        files={
            "file": (
                "portfolio.csv",
                b"symbol,quantity,price\nMSFT,10,420.25\nAAPL,20,195.10\nNVDA,5,130.50\n",
                "text/csv",
            ),
        },
    )
    assert upload.status_code == 201, upload.text
    artifact_id = upload.json()["id"]

    requested = e2e_http_client.post(
        f"{e2e_authenticated_client.base_url}/sessions/{session_id}/artifacts/{artifact_id}/analyze",
        headers=headers,
    )
    assert requested.status_code == 200, requested.text
    job = requested.json()
    assert job["artifact_id"] == artifact_id
    assert job["expected_rows"] == 3

    job = _wait_for_terminal_analysis(
        base_url=e2e_authenticated_client.base_url,
        headers=headers,
        session_id=session_id,
        artifact_id=artifact_id,
        job=job,
        client=e2e_http_client,
    )
    assert job["state"] == "completed", job
    assert job["successful_rows"] == job["expected_rows"] == 3, job
    assert job["failed_rows"] == 0, job
    assert job["successful_chunks"] == job["expected_chunks"], job
    assert job["failed_chunks"] == 0, job

    processing = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions/{session_id}/artifacts/{artifact_id}/processing",
        headers=headers,
    )
    assert processing.status_code == 200, processing.text
    manifest = processing.json()
    assert manifest["state"] == "ready", manifest
    assert manifest["total_rows"] == 3, manifest