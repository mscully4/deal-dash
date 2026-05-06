from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlparse


@dataclass
class Deal:
    title: str
    price: float
    discount: int
    url: str
    category: str
    stock: int
    retailer: str

    @classmethod
    def from_hit(cls, hit: dict[str, Any], retailer: str) -> "Deal":
        params = parse_qs(urlparse(hit["link"]).query)
        if "url" not in params:
            raise ValueError(f"No url param in link: {hit['link']!r}")
        return cls(
            title=hit["title"],
            price=float(hit["price"]),
            discount=int(hit["discount"]),
            url=params["url"][0],
            category=hit["category"],
            stock=int(hit["stock"]),
            retailer=retailer,
        )
