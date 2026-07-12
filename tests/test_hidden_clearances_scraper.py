from unittest.mock import MagicMock, patch

from deal_dash.lambdas.scrapers.hidden_clearances import HiddenClearancesScraperEvent, _run


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
        "category": "Plastic Edging",
    }
    return defaults | kwargs


async def _fake_search_feed(*_args, **_kwargs):
    yield _feed_item()


async def _fake_search_nearby(*_args, **_kwargs):
    yield _nearby_item()
    yield _nearby_item(productId="313296535", title="Grout")


@patch("deal_dash.lambdas.scrapers.hidden_clearances.DealStore")
@patch("deal_dash.lambdas.scrapers.hidden_clearances.HiddenClearancesClient")
async def test_run_writes_feed_and_nearby_deals(mock_client_cls, mock_store_cls):
    mock_client = MagicMock()
    mock_client.search_feed = _fake_search_feed
    mock_client.search_nearby = _fake_search_nearby
    mock_client_cls.return_value = mock_client
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    counts = await _run(HiddenClearancesScraperEvent())

    assert counts == {"feed": 1, "nearby": 2}
    assert mock_store.put_deal.call_count == 3


@patch("deal_dash.lambdas.scrapers.hidden_clearances.DealStore")
@patch("deal_dash.lambdas.scrapers.hidden_clearances.HiddenClearancesClient")
async def test_run_skips_nearby_when_disabled(mock_client_cls, mock_store_cls):
    mock_client = MagicMock()
    mock_client.search_feed = _fake_search_feed
    mock_client.search_nearby = _fake_search_nearby
    mock_client_cls.return_value = mock_client
    mock_store_cls.return_value = MagicMock()

    counts = await _run(HiddenClearancesScraperEvent(include_nearby=False))

    assert counts == {"feed": 1, "nearby": 0}
