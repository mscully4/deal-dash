from deal_dash.models import Deal


def test_deal_from_api_hit():
    hit = {
        "title": "Padlock Steel 2in",
        "price": 1.17,
        "discount": 91,
        "link": "https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F123",
        "category": "Hardware",
        "stock": 3,
    }
    deal = Deal.from_hit(hit, retailer="homedepot")
    assert deal.title == "Padlock Steel 2in"
    assert deal.price == 1.17
    assert deal.discount == 91
    assert deal.url == "https://www.homedepot.com/p/123"
    assert deal.category == "Hardware"
    assert deal.stock == 3
    assert deal.retailer == "homedepot"


def test_deal_from_hit_missing_link_raises():
    hit = {
        "title": "X",
        "price": 1.0,
        "discount": 50,
        "link": "https://www.rebelsavings.com/redirect",  # no ?url= param
        "category": "Tools",
        "stock": 1,
    }
    import pytest
    with pytest.raises(ValueError, match="url"):
        Deal.from_hit(hit, retailer="homedepot")
