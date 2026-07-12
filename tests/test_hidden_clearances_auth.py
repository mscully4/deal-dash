import json
from unittest.mock import MagicMock

import pytest
from pytest_httpx import HTTPXMock

from deal_dash.hidden_clearances.auth import _SUPABASE_URL, refresh_access_token


@pytest.fixture
def secrets_client():
    sm = MagicMock()
    sm.get_secret_value.return_value = {"SecretString": "old-refresh-token"}
    return sm


async def test_refresh_access_token_returns_new_access_token(
    httpx_mock: HTTPXMock, secrets_client
):
    httpx_mock.add_response(
        method="POST",
        url=f"{_SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        json={"access_token": "new-access", "refresh_token": "new-refresh"},
    )
    token = await refresh_access_token(secrets_client=secrets_client)
    assert token == "new-access"


async def test_refresh_access_token_writes_rotated_token_back(
    httpx_mock: HTTPXMock, secrets_client
):
    httpx_mock.add_response(json={"access_token": "new-access", "refresh_token": "new-refresh"})
    await refresh_access_token(secrets_client=secrets_client)

    secrets_client.put_secret_value.assert_called_once()
    assert secrets_client.put_secret_value.call_args.kwargs["SecretString"] == "new-refresh"


async def test_refresh_access_token_sends_stored_refresh_token(
    httpx_mock: HTTPXMock, secrets_client
):
    httpx_mock.add_response(json={"access_token": "a", "refresh_token": "b"})
    await refresh_access_token(secrets_client=secrets_client)

    body = json.loads(httpx_mock.get_request().content)
    assert body["refresh_token"] == "old-refresh-token"
