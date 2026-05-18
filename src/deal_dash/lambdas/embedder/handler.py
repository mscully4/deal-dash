import json
from typing import Any

import boto3
import httpx
from aws_lambda_powertools.utilities.data_classes import DynamoDBStreamEvent, event_source
from aws_lambda_powertools.utilities.data_classes.dynamo_db_stream_event import (
    DynamoDBRecordEventName,
)

from deal_dash.environment import Environment


_env = Environment.from_environment()
logger = _env.create_logger(__name__)

_NOTIFY_RETAILERS = {"homedepot"}
_MODEL_ID = "amazon.titan-embed-text-v2:0"
_DIMENSIONS = 256

_bot_token: str | None = None


def _get_bot_token() -> str:
    global _bot_token
    if _bot_token is None:
        sm = boto3.client("secretsmanager", region_name=_env.aws_region)
        _bot_token = sm.get_secret_value(SecretId=_env.discord_bot_token_arn)["SecretString"]
    return _bot_token


def _embed(text: str, bedrock: Any) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": _DIMENSIONS, "normalize": True})
    resp = bedrock.invoke_model(modelId=_MODEL_ID, body=body)
    return list(json.loads(resp["body"].read())["embedding"])


def _post_to_discord(doc: dict[str, Any]) -> None:
    custom_prefix = f"{doc['retailer']}:{doc['item_id']}"
    message = {
        "embeds": [
            {
                "title": doc["title"],
                "url": doc["url"],
                "color": 0x2ECC71,
                "fields": [
                    {"name": "Price", "value": f"${float(doc['price']):.2f}", "inline": True},
                    {"name": "Discount", "value": f"{doc['discount']}% off", "inline": True},
                    {"name": "Category", "value": doc["category"], "inline": True},
                    {
                        "name": "Location",
                        "value": f"{doc['city']}, {doc['state']}",
                        "inline": True,
                    },
                ],
            }
        ],
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


@event_source(data_class=DynamoDBStreamEvent)  # type: ignore[untyped-decorator]
def handler(event: DynamoDBStreamEvent, context: object) -> None:
    bedrock = _env.bedrock_client
    s3v = _env.s3vectors_client

    records = list(event.records)
    logger.info("batch received", extra={"size": len(records)})

    for record in records:
        event_name = record.event_name
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
        vector = _embed(text, bedrock)
        metadata: dict[str, Any] = {
            "retailer": retailer,
            "category": doc["category"],
            "discount": int(doc["discount"]),
            "price": float(doc["price"]),
        }
        liked = doc.get("liked")
        if isinstance(liked, bool):
            metadata["liked"] = liked

        s3v.put_vectors(
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
        ):
            _post_to_discord(doc)
