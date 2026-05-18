import json
import time
from functools import lru_cache
from typing import Any

import httpx
from aws_lambda_powertools.utilities.data_classes import DynamoDBStreamEvent
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBRecordEventName,
)

from deal_dash.environment import Environment


_env = Environment.from_environment()
logger = _env.create_logger(__name__)

_NOTIFY_RETAILERS: set[str] = {"homedepot"}
_MODEL_ID = "amazon.titan-embed-text-v2:0"
_DIMENSIONS = 256

_notified_upcs: dict[str, float] = {}


def _already_notified(upc: str, ttl: int = 7200) -> bool:
    cutoff = time.time() - ttl
    stale = [k for k, t in _notified_upcs.items() if t < cutoff]
    for k in stale:
        del _notified_upcs[k]
    return upc in _notified_upcs


def _mark_notified(upc: str) -> None:
    _notified_upcs[upc] = time.time()


@lru_cache
def _get_bot_token() -> str:
    return _env.secrets_manager_client.get_secret_value(SecretId=_env.discord_bot_token_arn)[
        "SecretString"
    ]


def _embed(text: str) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": _DIMENSIONS, "normalize": True})
    resp = _env.bedrock_client.invoke_model(modelId=_MODEL_ID, body=body)
    return list(json.loads(resp["body"].read())["embedding"])


def _post_to_discord(doc: dict[str, Any], liked: bool | None = None) -> None:
    custom_prefix = doc["upc"]
    fields: list[dict[str, Any]] = [
        {"name": "Price", "value": f"${float(doc['price']):.2f}", "inline": True},
        {"name": "Discount", "value": f"{doc['discount']}% off", "inline": True},
        {"name": "Category", "value": doc["category"], "inline": True},
        {
            "name": "Location",
            "value": f"{doc['address']}, {doc['city']}, {doc['state']}",
            "inline": True,
        },
    ]
    if liked is True:
        fields.append({"name": "Status", "value": "👍 Previously liked", "inline": True})
    elif liked is False:
        fields.append({"name": "Status", "value": "👎 Previously disliked", "inline": True})
    embed: dict[str, Any] = {
        "title": doc["title"],
        "url": doc["url"],
        "color": 0x2ECC71,
        "fields": fields,
    }
    if image_url := doc.get("image_url"):
        embed["image"] = {"url": image_url}
    message = {
        "embeds": [embed],
        "components": [
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 3,
                        "label": "👍 Like",
                        "custom_id": f"like:{custom_prefix}",
                    },
                    {
                        "type": 2,
                        "style": 4,
                        "label": "👎 Dislike",
                        "custom_id": f"dislike:{custom_prefix}",
                    },
                ],
            }
        ],
    }
    resp = httpx.post(
        f"https://discord.com/api/v10/channels/{_env.discord_channel_id}/messages",
        headers={"Authorization": f"Bot {_get_bot_token()}"},
        json=message,
        timeout=10.0,
    )
    resp.raise_for_status()
    logger.info("posted to Discord", extra={"upc": doc["upc"], "title": doc["title"]})


def handler(
    raw_event: dict[str, Any],
    context: Any,
) -> None:
    event: DynamoDBStreamEvent = DynamoDBStreamEvent(raw_event)

    records = list(event.records)
    logger.info("batch received", extra={"size": len(records)})

    for record in records:
        event_name = record.event_name
        if event_name is None:
            continue
        if event_name not in (DynamoDBRecordEventName.INSERT, DynamoDBRecordEventName.MODIFY):
            logger.info("skipping event", extra={"event": event_name.name})
            continue

        assert record.dynamodb is not None
        assert record.dynamodb.new_image is not None
        doc: dict[str, Any] = record.dynamodb.new_image
        upc = doc["upc"]
        retailer = doc["retailer"]
        logger.info(
            "processing record",
            extra={
                "event": event_name.name,
                "retailer": retailer,
                "upc": upc,
                "title": doc["title"],
            },
        )

        text = f"{doc['title']} {doc['category']} {doc.get('subcategory', '')}"
        vector = _embed(text)
        metadata: dict[str, Any] = {
            "retailer": retailer,
            "category": doc["category"],
            "discount": int(doc["discount"]),
            "price": float(doc["price"]),
        }

        existing = _env.s3vectors_client.get_vectors(
            vectorBucketName=_env.vector_bucket,
            indexName=_env.vector_index,
            keys=[upc],
            returnData=False,
            returnMetadata=True,
        ).get("vectors", [])
        existing_liked: bool | None = None
        if existing:
            liked_val = existing[0].get("metadata", {}).get("liked")
            if isinstance(liked_val, bool):
                existing_liked = liked_val
                metadata["liked"] = existing_liked

        _env.s3vectors_client.put_vectors(
            vectorBucketName=_env.vector_bucket,
            indexName=_env.vector_index,
            vectors=[{"key": upc, "data": {"float32": vector}, "metadata": metadata}],
        )
        logger.info("embedded", extra={"upc": upc})

        if (
            _env.discord_bot_token_arn
            and _env.discord_channel_id
            and event_name == DynamoDBRecordEventName.INSERT
            and retailer in _NOTIFY_RETAILERS
            and not _already_notified(upc)
        ):
            _post_to_discord(doc, liked=existing_liked)
            _mark_notified(upc)
