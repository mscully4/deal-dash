import time
from functools import lru_cache
from typing import Any

import httpx
from aws_lambda_powertools.metrics import Metrics, MetricUnit
from aws_lambda_powertools.utilities.data_classes import DynamoDBStreamEvent
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBRecordEventName,
)

from deal_dash.deals.environment import DealsEnvironment


_env = DealsEnvironment.from_environment()
logger = _env.create_logger(__name__)
metrics = Metrics(namespace="deal-dash", service="notifier")

_NOTIFY_RETAILERS: set[str] = {"homedepot", "lowes", "walmart"}
_MIN_NOTIFY_PRICE: float = 10.0
_RETAILER_DISPLAY: dict[str, str] = {
    "homedepot": "Home Depot",
    "lowes": "Lowe's",
    "walmart": "Walmart",
    "walgreens": "Walgreens",
    "tractorsupply": "Tractor Supply",
}

_notified_products: dict[str, float] = {}


def _already_notified(product_key: str, ttl: int = 7200) -> bool:
    cutoff = time.time() - ttl
    stale = [k for k, t in _notified_products.items() if t < cutoff]
    for k in stale:
        del _notified_products[k]
    return product_key in _notified_products


def _mark_notified(product_key: str) -> None:
    _notified_products[product_key] = time.time()


@lru_cache
def _get_bot_token() -> str:
    return _env.secrets_manager_client.get_secret_value(SecretId=_env.discord_bot_token_arn)[
        "SecretString"
    ]


def _post_to_discord(doc: dict[str, Any]) -> bool:
    """Posts a deal to Discord. Returns False (not an error) on rate limit
    so the caller can skip marking it notified without blocking/retrying
    the whole DDB stream batch."""
    retailer_display = _RETAILER_DISPLAY.get(doc["retailer"], doc["retailer"])
    fields: list[dict[str, Any]] = [
        {"name": "Retailer", "value": retailer_display, "inline": True},
        {"name": "Price", "value": f"${float(doc['price']):.2f}", "inline": True},
        {"name": "Discount", "value": f"{doc['discount']}% off", "inline": True},
        {"name": "Category", "value": doc["category"], "inline": True},
    ]
    location_bits = [b for b in (doc.get("address"), doc.get("city"), doc.get("state")) if b]
    if location_bits:
        fields.append({"name": "Location", "value": ", ".join(location_bits), "inline": True})

    embed: dict[str, Any] = {"title": doc["title"], "color": 0x2ECC71, "fields": fields}
    if url := doc.get("url"):
        embed["url"] = url
    if image_url := doc.get("image_url"):
        embed["image"] = {"url": image_url}

    target = f"{doc['product_key']}|{doc['store_key']}"
    components = [
        {
            "type": 1,
            "components": [
                {"type": 2, "style": 3, "label": "👍 Like", "custom_id": f"like:{target}"},
                {"type": 2, "style": 4, "label": "👎 Dislike", "custom_id": f"dislike:{target}"},
            ],
        }
    ]

    resp = httpx.post(
        f"https://discord.com/api/v10/channels/{_env.discord_channel_id}/messages",
        headers={"Authorization": f"Bot {_get_bot_token()}"},
        json={"embeds": [embed], "components": components},
        timeout=10.0,
    )
    if resp.status_code == 429:
        logger.warning(
            "discord rate limited, skipping",
            extra={"product_key": doc["product_key"]},
        )
        return False
    resp.raise_for_status()
    logger.info(
        "posted to Discord",
        extra={"product_key": doc["product_key"], "title": doc["title"]},
    )
    return True


@metrics.log_metrics(raise_on_empty_metrics=False)
def handler(raw_event: dict[str, Any], context: Any) -> None:
    event: DynamoDBStreamEvent = DynamoDBStreamEvent(raw_event)
    records = list(event.records)
    logger.info("batch received", extra={"size": len(records)})
    metrics.add_metric(name="RecordsProcessed", unit=MetricUnit.Count, value=len(records))

    for record in records:
        if record.event_name != DynamoDBRecordEventName.INSERT:
            continue

        assert record.dynamodb is not None
        assert record.dynamodb.new_image is not None
        doc: dict[str, Any] = record.dynamodb.new_image
        product_key = doc["product_key"]
        retailer = doc["retailer"]

        if not (_env.discord_bot_token_arn and _env.discord_channel_id):
            logger.info("notify skipped", extra={"product_key": product_key, "reason": "no_config"})
            metrics.add_metric(name="SkippedNoConfig", unit=MetricUnit.Count, value=1)
        elif retailer not in _NOTIFY_RETAILERS:
            logger.info("notify skipped", extra={"product_key": product_key, "reason": "retailer"})
            metrics.add_metric(name="SkippedRetailer", unit=MetricUnit.Count, value=1)
        elif float(doc["price"]) < _MIN_NOTIFY_PRICE:
            logger.info("notify skipped", extra={"product_key": product_key, "reason": "low_price"})
            metrics.add_metric(name="SkippedLowPrice", unit=MetricUnit.Count, value=1)
        elif _already_notified(product_key):
            logger.info("notify skipped", extra={"product_key": product_key, "reason": "dedupe"})
            metrics.add_metric(name="SkippedDedupe", unit=MetricUnit.Count, value=1)
        elif _post_to_discord(doc):
            _mark_notified(product_key)
            metrics.add_metric(name="Notified", unit=MetricUnit.Count, value=1)
        else:
            metrics.add_metric(name="RateLimited", unit=MetricUnit.Count, value=1)
