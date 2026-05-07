import json
from unittest.mock import AsyncMock, patch

import pytest
from pytest_httpx import HTTPXMock

from deal_dash.rebel_savings.client import RebelsavingsClient
from deal_dash.rebel_savings.models import Deal


SESSION_COOKIE = "fake-session-token"
LAT, LON, RADIUS = 30.5083, -97.6789, 25


@pytest.fixture
def client():
    c = RebelsavingsClient()
    c._cookie = SESSION_COOKIE  # pre-seed to skip Playwright in unit tests
    return c


def _make_doc(
    title: str = "Padlock Steel 2in",
    price: float = 1.17,
    discount: int = 91,
    link: str = "https://www.homedepot.com/p/Some-123?store=6541",
    category: str = "Hardware",
    subcategory: str = "Padlocks",
    stock: int = 3,
    upc: str = "012345678901",
    store: int = 123,
    address: str = "1234 Main St",
    city: str = "Austin",
    state: str = "TX",
) -> dict[str, object]:
    return {
        "title": title, "price": price, "discount": discount, "link": link,
        "category": category, "subcategory": subcategory, "stock": stock,
        "upc": upc, "store": store, "address": address, "city": city, "state": state,
    }


def _make_grouped_page(docs: list[dict], found: int | None = None) -> dict:
    if found is None:
        found = len(docs)
    return {
        "found": found,
        "grouped_hits": [{"group_key": [d["title"]], "hits": [{"document": d, "highlight": {}, "highlights": []}]} for d in docs],
    }


@pytest.fixture
def api_page_1():
    return _make_grouped_page([_make_doc()])


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
    assert body["retailer"] == "hd"
    assert body["sortBy"] == "dateAdded:desc"
    assert "location_geo:(30.5083, -97.6789, 25 mi)" in body["filterBy"]
    assert body["perPage"] == 100
    assert body["page"] == 1
    assert body["query"] == "*"
    assert body["groupBy"] == "title"


async def test_search_paginates(httpx_mock: HTTPXMock, client):
    doc = _make_doc(title="Item", price=1.0, discount=50, category="Tools", stock=1)
    httpx_mock.add_response(json=_make_grouped_page([doc] * 100, found=101))
    httpx_mock.add_response(json=_make_grouped_page([doc], found=101))

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


async def test_search_fetches_cookie_lazily(httpx_mock: HTTPXMock, api_page_1):
    httpx_mock.add_response(
        method="POST",
        url="https://www.rebelsavings.com/api/search",
        json=api_page_1,
    )
    with patch(
        "deal_dash.rebel_savings.client.get_session_cookie",
        new=AsyncMock(return_value="lazy-token"),
    ):
        c = RebelsavingsClient()
        async for _ in c.search("homedepot", LAT, LON, RADIUS):
            pass
        assert c._cookie == "lazy-token"
