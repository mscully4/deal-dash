import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import zipcodes
from aws_lambda_powertools.metrics import Metrics, MetricUnit, single_metric
from aws_lambda_powertools.utilities.parser import event_parser
from pydantic import BaseModel

from deal_dash.deals.dynamo import DealStore
from deal_dash.deals.environment import DealsEnvironment
from deal_dash.rebel_savings.adapter import to_deal
from deal_dash.rebel_savings.client import RebelsavingsClient
from deal_dash.rebel_savings.constants import (
    DEFAULT_DAYS,
    DEFAULT_RADIUS,
    DEFAULT_ZIP_CODE,
    Retailer,
)


_env = DealsEnvironment.from_environment()
logger = _env.create_logger(__name__)
metrics = Metrics(namespace="deal-dash", service="rebel-savings-scraper-v2")


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
    store = DealStore(env=_env)
    results: dict[Retailer, int] = {}
    for retailer in event.retailers:
        count = 0
        async for hit in client.search_raw(retailer, lat, lon, event.radius, since_ts):
            store.put_deal(to_deal(hit, retailer=retailer))
            count += 1
        logger.info("retailer scraped", extra={"retailer": retailer.value, "deals": count})
        with single_metric(
            name="DealsScraped",
            unit=MetricUnit.Count,
            value=count,
            namespace="deal-dash",
            default_dimensions={
                "service": "rebel-savings-scraper-v2",
                "retailer": retailer.value,
            },
        ):
            pass
        results[retailer] = count
    return results


@metrics.log_metrics(raise_on_empty_metrics=False)
@event_parser(model=RebelSavingsScraperEvent)  # type: ignore[untyped-decorator]
def handler(event: RebelSavingsScraperEvent, context: Any) -> dict[str, Any]:
    logger.info(
        "scraper starting",
        extra={"zip": event.zip_code, "retailers": [r.value for r in event.retailers]},
    )
    results = asyncio.run(_run(event))
    total = sum(results.values())
    metrics.add_metric(name="TotalDealsScraped", unit=MetricUnit.Count, value=total)
    logger.info("scraper done", extra={"results": {k.value: v for k, v in results.items()}})
    return {"status": "ok", "deals": {k.value: v for k, v in results.items()}}
