import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from deal_dash.deals.models import Deal


# Both Home Depot (`?store=`) and Lowe's (`?store_code=`) URLs embed the
# retailer's own product ID as the last path segment before the query
# string — this is the ID Hidden Clearances calls `productId`.
_PRODUCT_ID_RE = re.compile(r"/(\d+)\?")


def _extract_canonical_id(url: str) -> str | None:
    match = _PRODUCT_ID_RE.search(url)
    return match.group(1) if match else None


def to_deal(hit: dict[str, Any], retailer: str) -> Deal:
    link = hit["link"]
    params = parse_qs(urlparse(link).query)
    url = params["url"][0] if "url" in params else link
    canonical_id = _extract_canonical_id(url)

    return Deal(
        source="rebelsavings",
        retailer=retailer,
        canonical_id=canonical_id,
        fallback_id=None if canonical_id else hit["upc"],
        title=hit["title"],
        price=float(hit["price"]),
        discount=int(hit["discount"]),
        category=hit["category"],
        subcategory=hit.get("subcategory", ""),
        url=url,
        image_url=hit.get("image_url"),
        stock=int(hit["stock"]),
        store=int(hit["store"]),
        address=hit["address"],
        city=hit["city"],
        state=hit["state"],
        upc=hit.get("upc"),
    )
