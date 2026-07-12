import pytest

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
    }
    return Deal(**(defaults | kwargs))


def test_product_key_uses_canonical_id():
    deal = _make_deal()
    assert deal.product_key == "homedepot#330884657"


def test_store_key_for_in_store_deal():
    deal = _make_deal(store=509)
    assert deal.store_key == "store#509"


def test_store_key_for_online_deal():
    deal = _make_deal(store=None)
    assert deal.store_key == "online"


def test_product_key_falls_back_to_source_scoped_id_when_locked():
    deal = _make_deal(source="hiddenclearances", canonical_id=None, fallback_id="787a69a1-uuid")
    assert deal.product_key == "homedepot#hiddenclearances:787a69a1-uuid"


def test_requires_canonical_id_or_fallback_id():
    with pytest.raises(ValueError, match="canonical_id or fallback_id"):
        _make_deal(canonical_id=None, fallback_id=None)
