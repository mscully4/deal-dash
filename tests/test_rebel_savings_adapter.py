from deal_dash.rebel_savings.adapter import to_deal


def _make_hit(**kwargs) -> dict:
    defaults = {
        "title": "Milwaukee PACKOUT Rack Kit",
        "price": 800.0,
        "discount": 60,
        "link": "https://www.homedepot.com/p/Milwaukee-PACKOUT-Rack-Kit-48-21-8070/330884657?store=509",
        "category": "Garage",
        "subcategory": "Tool Storage",
        "stock": 1,
        "upc": "045242336036",
        "store": 509,
        "address": "11301 Lakeline Blvd, Austin, TX 78717",
        "city": "Austin",
        "state": "TX",
    }
    return defaults | kwargs


def test_to_deal_extracts_home_depot_canonical_id():
    deal = to_deal(_make_hit(), retailer="homedepot")
    assert deal.canonical_id == "330884657"
    assert deal.product_key == "homedepot#330884657"
    assert deal.upc == "045242336036"


def test_to_deal_extracts_lowes_canonical_id():
    hit = _make_hit(
        link="https://www.lowes.com/pd/GE-1-7-cu-ft-Over-the-Range-Microwave/1000074205?store_code=1725",
        store=1725,
    )
    deal = to_deal(hit, retailer="lowes")
    assert deal.canonical_id == "1000074205"


def test_to_deal_falls_back_to_upc_when_no_id_in_url():
    hit = _make_hit(link="https://www.walmart.com/ip/Some-Product/16360552809")
    deal = to_deal(hit, retailer="walmart")
    assert deal.canonical_id is None
    assert deal.fallback_id == "045242336036"
    assert deal.product_key == "walmart#rebelsavings:045242336036"


def test_to_deal_resolves_redirect_link():
    hit = _make_hit(
        link="https://www.rebelsavings.com/redirect?url=https%3A%2F%2Fwww.homedepot.com%2Fp%2F330884657%3Fstore%3D509"
    )
    deal = to_deal(hit, retailer="homedepot")
    assert deal.url == "https://www.homedepot.com/p/330884657?store=509"
    assert deal.canonical_id == "330884657"
