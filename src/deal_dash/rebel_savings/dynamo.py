import os
from decimal import Decimal
from typing import Any

import boto3

from deal_dash.rebel_savings.models import Deal


_TABLE_NAME = os.environ.get("DEALS_TABLE", "rebel-savings-deals")
_REGION = os.environ.get("AWS_REGION", "us-east-2")


class DealStore:
    def __init__(self, table: Any = None) -> None:
        if table is None:
            dynamodb = boto3.resource("dynamodb", region_name=_REGION)
            self._table: Any = dynamodb.Table(_TABLE_NAME)
        else:
            self._table = table

    def put_deal(self, deal: Deal) -> None:
        self._table.put_item(
            Item={
                "retailer": deal.retailer,
                "item_id": deal.item_id,
                "title": deal.title,
                "price": Decimal(str(deal.price)),
                "discount": deal.discount,
                "url": deal.url,
                "category": deal.category,
                "subcategory": deal.subcategory,
                "stock": deal.stock,
                "upc": deal.upc,
                "store": deal.store,
                "address": deal.address,
                "city": deal.city,
                "state": deal.state,
            }
        )
