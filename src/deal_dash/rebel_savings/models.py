from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, computed_field


class Deal(BaseModel):
    title: str
    price: float
    discount: int
    url: str
    category: str
    subcategory: str
    stock: int
    retailer: str
    upc: str
    store: int
    address: str
    city: str
    state: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def item_id(self) -> str:
        return f"{self.upc}#{self.store}"

    @classmethod
    def from_hit(cls, hit: dict[str, Any], retailer: str) -> "Deal":
        link = hit["link"]
        params = parse_qs(urlparse(link).query)
        url = params["url"][0] if "url" in params else link
        return cls(
            title=hit["title"],
            price=float(hit["price"]),
            discount=int(hit["discount"]),
            url=url,
            category=hit["category"],
            subcategory=hit.get("subcategory", ""),
            stock=int(hit["stock"]),
            retailer=retailer,
            upc=hit["upc"],
            store=int(hit["store"]),
            address=hit["address"],
            city=hit["city"],
            state=hit["state"],
        )
