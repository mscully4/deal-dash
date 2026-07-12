from unittest.mock import MagicMock, patch

from deal_dash.lambdas.scrapers.rebel_savings_v2 import RebelSavingsScraperEvent, _run
from deal_dash.rebel_savings.constants import Retailer


def _hit(**kwargs) -> dict:
    defaults = {
        "title": "Milwaukee PACKOUT Rack Kit",
        "price": 800.0,
        "discount": 60,
        "link": "https://www.homedepot.com/p/x/330884657?store=509",
        "category": "Garage",
        "subcategory": "Tool Storage",
        "stock": 1,
        "upc": "045242336036",
        "store": 509,
        "address": "11301 Lakeline Blvd",
        "city": "Austin",
        "state": "TX",
    }
    return defaults | kwargs


async def _fake_search_raw(*_args, **_kwargs):
    yield _hit()
    yield _hit(store=6570, link="https://www.homedepot.com/p/x/330884657?store=6570")


@patch("deal_dash.lambdas.scrapers.rebel_savings_v2._zip_to_latlon", return_value=(30.4, -97.75))
@patch("deal_dash.lambdas.scrapers.rebel_savings_v2.DealStore")
@patch("deal_dash.lambdas.scrapers.rebel_savings_v2.RebelsavingsClient")
async def test_run_writes_deals_for_each_retailer(mock_client_cls, mock_store_cls, _mock_latlon):
    mock_client = MagicMock()
    mock_client.search_raw = _fake_search_raw
    mock_client_cls.return_value = mock_client
    mock_store = MagicMock()
    mock_store_cls.return_value = mock_store

    results = await _run(RebelSavingsScraperEvent(retailers=[Retailer.HOMEDEPOT]))

    assert results == {Retailer.HOMEDEPOT: 2}
    assert mock_store.put_deal.call_count == 2
    deal = mock_store.put_deal.call_args_list[0].args[0]
    assert deal.canonical_id == "330884657"
    assert deal.source == "rebelsavings"
