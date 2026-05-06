import json
import pytest
from pytest_httpx import HTTPXMock
from deal_dash.client import RebelsavingsClient
from deal_dash.models import Deal


SESSION_COOKIE = "fake-session-token"
LAT, LON, RADIUS = 30.5083, -97.6789, 25


@pytest.fixture
def client():
    return RebelsavingsClient(session_cookie=SESSION_COOKIE)


@pytest.fixture
def api_page_1():
    return {
        "found": 1,
        "hits": [
            {
                "title": "Padlock Steel 2in",
                "price": 1.17,
                "discount": 91,
                "link": "https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F123",
                "category": "Hardware",
                "stock": 3,
            }
        ],
    }


async def test_search_returns_deals(httpx_mock: HTTPXMock, client, api_page_1):
    httpx_mock.add_response(
        method="POST",
        url="https://www.rebelsavings.com/api/search",
        json=api_page_1,
    )
    deals = []
    async for deal in client.search("homedepot", LAT, LON, RADIUS):
        deals.append(deal)

    assert len(deals) == 1
    assert isinstance(deals[0], Deal)
    assert deals[0].title == "Padlock Steel 2in"
    assert deals[0].retailer == "homedepot"


async def test_search_sends_correct_payload(httpx_mock: HTTPXMock, client, api_page_1):
    httpx_mock.add_response(
        method="POST",
        url="https://www.rebelsavings.com/api/search",
        json=api_page_1,
    )
    async for _ in client.search("homedepot", LAT, LON, RADIUS):
        pass

    request = httpx_mock.get_request()
    body = json.loads(request.content)
    assert body["retailer"] == "homedepot"
    assert body["sortBy"] == "discount:desc"
    assert "location_geo:(30.5083, -97.6789, 25 mi)" in body["filterBy"]
    assert body["perPage"] == 100
    assert body["page"] == 1
    assert body["query"] == "*"


async def test_search_paginates(httpx_mock: HTTPXMock, client):
    page_hit = {
        "title": "Item",
        "price": 1.0,
        "discount": 50,
        "link": "https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F1",
        "category": "Tools",
        "stock": 1,
    }
    # 101 total found, perPage=100 → 2 pages
    httpx_mock.add_response(json={"found": 101, "hits": [page_hit] * 100})
    httpx_mock.add_response(json={"found": 101, "hits": [page_hit]})

    deals = []
    async for deal in client.search("homedepot", LAT, LON, RADIUS):
        deals.append(deal)

    assert len(deals) == 101
    assert len(httpx_mock.get_requests()) == 2


async def test_search_sets_session_cookie(httpx_mock: HTTPXMock, client, api_page_1):
    httpx_mock.add_response(
        method="POST",
        url="https://www.rebelsavings.com/api/search",
        json=api_page_1,
    )
    async for _ in client.search("homedepot", LAT, LON, RADIUS):
        pass

    request = httpx_mock.get_request()
    assert "rs_session=fake-session-token" in request.headers["cookie"]
