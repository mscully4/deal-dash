from decimal import Decimal
from unittest.mock import MagicMock

from deal_dash.rebel_savings.dynamo import DealStore
from deal_dash.rebel_savings.models import Deal


def _make_deal(**kwargs) -> Deal:
    defaults: dict = {
        "title": "Padlock Steel 2in",
        "price": 1.17,
        "discount": 91,
        "url": "https://www.homedepot.com/p/123",
        "category": "Hardware",
        "subcategory": "Padlocks",
        "stock": 3,
        "retailer": "homedepot",
        "upc": "012345678901",
        "store": 123,
        "address": "1234 Main St",
        "city": "Austin",
        "state": "TX",
    }
    return Deal(**(defaults | kwargs))


def test_put_deal_writes_correct_item():
    mock_table = MagicMock()
    store = DealStore(table=mock_table)
    store.put_deal(_make_deal())

    mock_table.put_item.assert_called_once()
    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["retailer"] == "homedepot"
    assert item["item_id"] == "012345678901#123"
    assert item["title"] == "Padlock Steel 2in"
    assert item["discount"] == 91
    assert item["upc"] == "012345678901"
    assert item["store"] == 123
    assert item["city"] == "Austin"
    assert item["state"] == "TX"


def test_put_deal_price_stored_as_decimal():
    mock_table = MagicMock()
    store = DealStore(table=mock_table)
    store.put_deal(_make_deal(price=4.48))

    item = mock_table.put_item.call_args.kwargs["Item"]
    assert isinstance(item["price"], Decimal)
    assert item["price"] == Decimal("4.48")


def test_put_deal_item_id_matches_upc_store():
    mock_table = MagicMock()
    store = DealStore(table=mock_table)
    store.put_deal(_make_deal(upc="999888777666", store=42))

    item = mock_table.put_item.call_args.kwargs["Item"]
    assert item["item_id"] == "999888777666#42"
