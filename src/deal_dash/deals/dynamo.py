import time
from decimal import Decimal
from typing import Any

from deal_dash.deals.environment import DealsEnvironment
from deal_dash.deals.models import Deal


class DealStore:
    def __init__(self, env: DealsEnvironment | None = None, table: Any = None) -> None:
        if table is not None:
            self._table: Any = table
        else:
            self._table = (env or DealsEnvironment.from_environment()).deals_table_resource

    def put_deal(self, deal: Deal) -> None:
        fields: dict[str, Any] = {
            "retailer": deal.retailer,
            "canonical_id": deal.canonical_id,
            "title": deal.title,
            "price": Decimal(str(deal.price)),
            "original_price": (
                Decimal(str(deal.original_price)) if deal.original_price is not None else None
            ),
            "discount": deal.discount,
            "category": deal.category,
            "subcategory": deal.subcategory,
            "url": deal.url,
            "image_url": deal.image_url,
            "stock": deal.stock,
            "store": deal.store,
            "address": deal.address,
            "city": deal.city,
            "state": deal.state,
            "upc": deal.upc,
            "last_updated": int(time.time()),
            f"{deal.source}_id": deal.canonical_id or deal.fallback_id,
        }

        names: dict[str, str] = {}
        values: dict[str, Any] = {":sources": {deal.source}}
        set_parts: list[str] = []

        for i, (field, value) in enumerate(fields.items()):
            if value is None:
                continue
            alias, vkey = f"#f{i}", f":v{i}"
            names[alias] = field
            values[vkey] = value
            set_parts.append(f"{alias} = {vkey}")

        self._table.update_item(
            Key={"product_key": deal.product_key, "store_key": deal.store_key},
            UpdateExpression=f"SET {', '.join(set_parts)} ADD sources :sources",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
