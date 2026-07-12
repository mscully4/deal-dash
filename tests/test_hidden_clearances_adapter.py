from deal_dash.hidden_clearances.adapter import to_deal


def _feed_item(**kwargs) -> dict:
    defaults = {
        "id": "144a56e1-f574-45ff-8d1e-098d290a7749",
        "title": "American Tourister Luggage Set",
        "retailer": "walmart",
        "kind": "online",
        "locked": False,
        "price": "109.00",
        "originalPrice": "599.99",
        "discountPercent": 82,
        "productId": None,
        "category": None,
        "dealLink": "https://www.walmart.com/ip/some-item/123",
        "imageUrl": "https://cdn.frugalseasons.com/x.jpg",
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
        "imageUrl": "https://images.thdstatic.com/x.jpg",
    }
    return defaults | kwargs


def test_null_category_falls_back_to_uncategorized():
    # category is a GSI sort key — DynamoDB rejects an empty string there.
    deal = to_deal(_feed_item(category=None))
    assert deal.category == "Uncategorized"


def test_null_discount_percent_defaults_to_zero():
    deal = to_deal(_feed_item(discountPercent=None))
    assert deal.discount == 0


def test_retailer_normalized_to_match_rebel_savings():
    deal = to_deal(_nearby_item(retailer="home_depot"))
    assert deal.retailer == "homedepot"
    assert deal.product_key == "homedepot#205794807"


def test_online_deal_has_no_store():
    deal = to_deal(_feed_item())
    assert deal.store is None
    assert deal.store_key == "online"


def test_locked_lead_falls_back_to_hc_id():
    item = _feed_item(
        title="24-in Front Control Built-in Dishwasher",
        retailer="lowes",
        kind="in_store",
        locked=True,
        productId=None,
    )
    deal = to_deal(item)
    assert deal.canonical_id is None
    assert deal.fallback_id == item["id"]
    assert deal.product_key == f"lowes#hiddenclearances:{item['id']}"


def test_nearby_item_has_numeric_store_and_canonical_id():
    deal = to_deal(_nearby_item())
    assert deal.store == 8439
    assert deal.store_key == "store#8439"
    assert deal.canonical_id == "205794807"
    assert deal.product_key == "homedepot#205794807"


def test_nearby_item_uses_store_name_as_address():
    deal = to_deal(_nearby_item())
    assert deal.address == "Hutto"
