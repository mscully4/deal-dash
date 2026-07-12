from unittest.mock import AsyncMock, patch

import pytest
from pytest_httpx import HTTPXMock

from deal_dash.hidden_clearances.client import HiddenClearancesClient


@pytest.fixture
def client():
    c = HiddenClearancesClient()
    c._access_token = "fake-token"
    return c


def _feed_item(**kwargs) -> dict:
    defaults = {
        "id": "144a56e1-uuid",
        "title": "American Tourister Luggage Set",
        "retailer": "walmart",
        "kind": "online",
        "locked": False,
        "price": "109.00",
        "originalPrice": "599.99",
        "discountPercent": 82,
        "productId": None,
        "category": None,
        "isInStock": True,
    }
    return defaults | kwargs


def _nearby_item(**kwargs) -> dict:
    defaults = {
        "retailer": "home_depot",
        "productId": "205794807",
        "title": "Contractor Pack Nylon Spikes",
        "storeNumber": "8439",
        "storeName": "Hutto",
        "price": 4.0,
        "originalPrice": 39.97,
        "discountPercent": 90,
    }
    return defaults | kwargs


async def test_search_feed_returns_items(httpx_mock: HTTPXMock, client):
    httpx_mock.add_response(json={"success": True, "data": [_feed_item()]})
    items = [item async for item in client.search_feed()]
    assert len(items) == 1
    assert items[0]["title"] == "American Tourister Luggage Set"


async def test_search_feed_sends_bearer_token(httpx_mock: HTTPXMock, client):
    httpx_mock.add_response(json={"success": True, "data": [_feed_item()]})
    async for _ in client.search_feed():
        pass
    request = httpx_mock.get_request()
    assert request.headers["authorization"] == "Bearer fake-token"
    assert "kind=curated" in str(request.url)


async def test_search_feed_paginates_until_short_page(httpx_mock: HTTPXMock, client):
    httpx_mock.add_response(json={"success": True, "data": [_feed_item()] * 50})
    httpx_mock.add_response(json={"success": True, "data": [_feed_item()]})
    items = [item async for item in client.search_feed()]
    assert len(items) == 51
    assert len(httpx_mock.get_requests()) == 2


async def test_search_feed_refreshes_token_lazily(httpx_mock: HTTPXMock):
    httpx_mock.add_response(json={"success": True, "data": [_feed_item()]})
    with patch(
        "deal_dash.hidden_clearances.client.refresh_access_token",
        new=AsyncMock(return_value="lazy-token"),
    ):
        c = HiddenClearancesClient()
        async for _ in c.search_feed():
            pass
        assert c._access_token == "lazy-token"


async def test_search_nearby_returns_items(httpx_mock: HTTPXMock, client):
    httpx_mock.add_response(json={"success": True, "data": [_nearby_item()]})
    items = [item async for item in client.search_nearby()]
    assert len(items) == 1
    assert items[0]["storeNumber"] == "8439"
