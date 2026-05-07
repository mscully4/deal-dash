import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import zipcodes
from pydantic import BaseModel

from deal_dash.environment import Environment
from deal_dash.rebel_savings.client import RebelsavingsClient
from deal_dash.rebel_savings.constants import (
    DEFAULT_DAYS,
    DEFAULT_RADIUS,
    DEFAULT_ZIP_CODE,
    Retailer,
)
from deal_dash.rebel_savings.dynamo import DealStore


_env = Environment.from_environment()


class RebelSavingsScraperEvent(BaseModel):
    zip_code: str = DEFAULT_ZIP_CODE
    radius: float = DEFAULT_RADIUS
    days: int = DEFAULT_DAYS
    retailers: list[Retailer] = list(Retailer)


def _zip_to_latlon(zip_code: str) -> tuple[float, float]:
    result = zipcodes.matching(zip_code)
    rec = result[0]
    return float(rec["lat"]), float(rec["long"])


async def _run(event: RebelSavingsScraperEvent) -> dict[str, int]:
    lat, lon = _zip_to_latlon(event.zip_code)
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=event.days)).timestamp())
    client = RebelsavingsClient()
    store = DealStore(table=_env.deals_table_resource)
    results: dict[str, int] = {}
    for retailer in event.retailers:
        count = 0
        async for deal in client.search(retailer, lat, lon, event.radius, since_ts):
            store.put_deal(deal)
            count += 1
        results[retailer] = count
    return results


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    parsed = RebelSavingsScraperEvent.model_validate(event)
    results = asyncio.run(_run(parsed))
    return {"status": "ok", "deals": results}
