from typing import Literal

from pydantic import BaseModel, computed_field, model_validator


Source = Literal["rebelsavings", "hiddenclearances"]


class Deal(BaseModel):
    """Source-agnostic deal record for the deal-dash-deals table.

    `canonical_id` is the retailer's own product ID (e.g. Home Depot's
    Internet #), the shared key both sources resolve to. Hidden Clearances
    omits it for locked/paywalled deals — `fallback_id` (a source-specific
    id, e.g. HC's opaque uuid) keeps those deals addressable without
    dedupe against the other source.
    """

    source: Source
    retailer: str
    canonical_id: str | None = None
    fallback_id: str | None = None
    title: str
    price: float
    original_price: float | None = None
    discount: int
    category: str
    subcategory: str = ""
    url: str | None = None
    image_url: str | None = None
    stock: int | None = None
    store: int | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    upc: str | None = None

    @model_validator(mode="after")
    def _require_an_id(self) -> "Deal":
        if self.canonical_id is None and self.fallback_id is None:
            raise ValueError("Deal requires canonical_id or fallback_id")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def product_key(self) -> str:
        product_id = self.canonical_id or f"{self.source}:{self.fallback_id}"
        return f"{self.retailer}#{product_id}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def store_key(self) -> str:
        return f"store#{self.store}" if self.store is not None else "online"
