import httpx
import pytest


@pytest.mark.e2e
def test_health_endpoint_is_reachable(e2e_client_settings, e2e_http_client: httpx.Client) -> None:
    response = e2e_http_client.get(
        f"{e2e_client_settings.e2e_api_base_url.rstrip('/')}/health"
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


@pytest.mark.e2e
def test_authenticated_sessions_list_returns_200(
    e2e_authenticated_client,
    e2e_http_client: httpx.Client,
) -> None:
    response = e2e_http_client.get(
        f"{e2e_authenticated_client.base_url}/sessions",
        headers=e2e_authenticated_client.authorization_header,
    )

    assert response.status_code == 200, response.text
