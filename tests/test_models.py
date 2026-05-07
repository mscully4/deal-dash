import pytest

from deal_dash.rebel_savings.models import Deal


def _make_hit(**kwargs) -> dict:
    defaults = {
        "title": "Padlock Steel 2in",
        "price": 1.17,
        "discount": 91,
        "link": "https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F123",
        "category": "Hardware",
        "subcategory": "Padlocks",
        "stock": 3,
        "upc": "012345678901",
        "store": 123,
        "address": "1234 Main St",
        "city": "Austin",
        "state": "TX",
    }
    return defaults | kwargs


def test_deal_from_api_hit():
    deal = Deal.from_hit(_make_hit(), retailer="homedepot")
    assert deal.title == "Padlock Steel 2in"
    assert deal.price == 1.17
    assert deal.discount == 91
    assert deal.url == "https://www.homedepot.com/p/123"
    assert deal.category == "Hardware"
    assert deal.stock == 3
    assert deal.retailer == "homedepot"
    assert deal.upc == "012345678901"
    assert deal.store == 123
    assert deal.item_id == "012345678901#123"


def test_deal_from_hit_direct_link():
    link = "https://www.homedepot.com/p/Some-Product-123/456789?store=6541"
    deal = Deal.from_hit(_make_hit(link=link), retailer="homedepot")
    assert deal.url == link
