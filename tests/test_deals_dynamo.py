from decimal import Decimal
from unittest.mock import MagicMock

from deal_dash.deals.dynamo import DealStore
from deal_dash.deals.models import Deal


def _make_deal(**kwargs) -> Deal:
    defaults: dict = {
        "source": "rebelsavings",
        "retailer": "homedepot",
        "canonical_id": "330884657",
        "title": "Milwaukee PACKOUT Rack Kit",
        "price": 800.0,
        "discount": 60,
        "category": "Garage",
        "subcategory": "Tool Storage",
        "store": 509,
        "upc": "045242336036",
    }
    return Deal(**(defaults | kwargs))


def _call_kwargs(mock_table: MagicMock) -> dict:
    return mock_table.update_item.call_args.kwargs


def _resolved_fields(mock_table: MagicMock) -> dict:
    kwargs = _call_kwargs(mock_table)
    names = kwargs["ExpressionAttributeNames"]
    values = kwargs["ExpressionAttributeValues"]
    return {names[alias]: values[f":v{alias[2:]}"] for alias in names}


def test_put_deal_uses_product_and_store_key():
    mock_table = MagicMock()
    DealStore(table=mock_table).put_deal(_make_deal())

    key = _call_kwargs(mock_table)["Key"]
    assert key == {"product_key": "homedepot#330884657", "store_key": "store#509"}


def test_put_deal_writes_expected_fields():
    mock_table = MagicMock()
    DealStore(table=mock_table).put_deal(_make_deal())

    fields = _resolved_fields(mock_table)
    assert fields["retailer"] == "homedepot"
    assert fields["title"] == "Milwaukee PACKOUT Rack Kit"
    assert fields["price"] == Decimal("800.0")
    assert fields["upc"] == "045242336036"
    assert fields["rebelsavings_id"] == "330884657"


def test_put_deal_omits_none_fields():
    mock_table = MagicMock()
    DealStore(table=mock_table).put_deal(_make_deal(image_url=None, stock=None))

    fields = _resolved_fields(mock_table)
    assert "image_url" not in fields
    assert "stock" not in fields


def test_put_deal_adds_source_to_sources_set():
    mock_table = MagicMock()
    DealStore(table=mock_table).put_deal(_make_deal(source="hiddenclearances"))

    values = _call_kwargs(mock_table)["ExpressionAttributeValues"]
    assert values[":sources"] == {"hiddenclearances"}
    assert "ADD sources :sources" in _call_kwargs(mock_table)["UpdateExpression"]
