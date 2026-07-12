import asyncio
from typing import Any

from aws_lambda_powertools.metrics import Metrics, MetricUnit, single_metric
from aws_lambda_powertools.utilities.parser import event_parser
from pydantic import BaseModel

from deal_dash.deals.dynamo import DealStore
from deal_dash.deals.environment import DealsEnvironment
from deal_dash.hidden_clearances.adapter import to_deal
from deal_dash.hidden_clearances.client import HiddenClearancesClient


_env = DealsEnvironment.from_environment()
logger = _env.create_logger(__name__)
metrics = Metrics(namespace="deal-dash", service="hidden-clearances-scraper")


class HiddenClearancesScraperEvent(BaseModel):
    include_feed: bool = True
    include_nearby: bool = True


async def _run(event: HiddenClearancesScraperEvent) -> dict[str, int]:
    client = HiddenClearancesClient(env=_env)
    store = DealStore(env=_env)
    counts: dict[str, int] = {"feed": 0, "nearby": 0}

    if event.include_feed:
        async for item in client.search_feed():
            store.put_deal(to_deal(item))
            counts["feed"] += 1
        logger.info("feed scraped", extra={"deals": counts["feed"]})

    if event.include_nearby:
        async for item in client.search_nearby():
            store.put_deal(to_deal(item))
            counts["nearby"] += 1
        logger.info("nearby scraped", extra={"deals": counts["nearby"]})

    for kind, count in counts.items():
        with single_metric(
            name="DealsScraped",
            unit=MetricUnit.Count,
            value=count,
            namespace="deal-dash",
            default_dimensions={"service": "hidden-clearances-scraper", "kind": kind},
        ):
            pass

    return counts


@metrics.log_metrics(raise_on_empty_metrics=False)
@event_parser(model=HiddenClearancesScraperEvent)  # type: ignore[untyped-decorator]
def handler(event: HiddenClearancesScraperEvent, context: Any) -> dict[str, Any]:
    logger.info(
        "scraper starting",
        extra={"include_feed": event.include_feed, "include_nearby": event.include_nearby},
    )
    results = asyncio.run(_run(event))
    total = sum(results.values())
    metrics.add_metric(name="TotalDealsScraped", unit=MetricUnit.Count, value=total)
    logger.info("scraper done", extra={"results": results})
    return {"status": "ok", "deals": results}
