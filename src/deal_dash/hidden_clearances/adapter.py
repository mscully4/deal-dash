from typing import Any

from deal_dash.deals.models import Deal


def to_deal(item: dict[str, Any]) -> Deal:
    """Map a Hidden Clearances item to a Deal.

    Two shapes come out of the client: `/feed` items (online deals and
    locked in-store leads — no numeric store #, may have `productId: null`
    when locked) and `/clearance/nearby` items (unlocked in-store finds,
    always have a numeric `storeNumber`). Distinguish by the presence of
    `storeNumber`.
    """
    is_nearby = "storeNumber" in item
    canonical_id = item.get("productId")
    store = int(item["storeNumber"]) if is_nearby and item.get("storeNumber") else None

    return Deal(
        source="hiddenclearances",
        # Hidden Clearances uses snake_case retailer names ("home_depot");
        # Rebel Savings doesn't ("homedepot") — normalize so canonical_id
        # matches actually dedupe across sources instead of silently
        # forking into two separate product_keys.
        retailer=item["retailer"].replace("_", ""),
        canonical_id=str(canonical_id) if canonical_id else None,
        fallback_id=None if canonical_id else item["id"],
        title=item["title"],
        price=float(item["price"]),
        original_price=(
            float(item["originalPrice"]) if item.get("originalPrice") is not None else None
        ),
        discount=int(item.get("discountPercent") or 0),
        # category is the retailer-category-index GSI sort key — DynamoDB
        # rejects an empty string there, so fall back to a real value.
        category=item.get("category") or "Uncategorized",
        url=item.get("dealLink"),
        image_url=item.get("imageUrl"),
        stock=item.get("stockQty"),
        store=store,
        address=item.get("storeName") if is_nearby else None,
    )
