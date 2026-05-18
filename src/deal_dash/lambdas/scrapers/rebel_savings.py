import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import zipcodes
from aws_lambda_powertools.utilities.parser import event_parser
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
logger = _env.create_logger(__name__)


class RebelSavingsScraperEvent(BaseModel):
    zip_code: str = DEFAULT_ZIP_CODE
    radius: float = DEFAULT_RADIUS
    days: int = DEFAULT_DAYS
    retailers: list[Retailer] = list(Retailer)


def _zip_to_latlon(zip_code: str) -> tuple[float, float]:
    result = zipcodes.matching(zip_code)
    rec = result[0]
    return float(rec["lat"]), float(rec["long"])


async def _run(event: RebelSavingsScraperEvent) -> dict[Retailer, int]:
    lat, lon = _zip_to_latlon(event.zip_code)
    since_ts = int((datetime.now(timezone.utc) - timedelta(days=event.days)).timestamp())
    logger.info(
        "scrape params",
        extra={
            "zip": event.zip_code,
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "days": event.days,
            "retailers": [r.value for r in event.retailers],
        },
    )
    client = RebelsavingsClient()
    store = DealStore(table=_env.deals_table_resource)
    results: dict[Retailer, int] = {}
    for retailer in event.retailers:
        count = 0
        async for deal in client.search(retailer, lat, lon, event.radius, since_ts):
            store.put_deal(deal)
            count += 1
        logger.info("retailer scraped", extra={"retailer": retailer.value, "deals": count})
        results[retailer] = count
    return results


@event_parser(model=RebelSavingsScraperEvent)  # type: ignore[untyped-decorator]
def handler(event: RebelSavingsScraperEvent, context: Any) -> dict[str, Any]:
    logger.info(
        "scraper starting",
        extra={"zip": event.zip_code, "retailers": [r.value for r in event.retailers]},
    )
    results = asyncio.run(_run(event))
    logger.info("scraper done", extra={"results": {k.value: v for k, v in results.items()}})
    return {"status": "ok", "deals": {k.value: v for k, v in results.items()}}
