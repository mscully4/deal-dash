from __future__ import annotations

import json
from typing import Any

from aws_lambda_powertools.metrics import Metrics, MetricUnit
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

from deal_dash.deals.environment import DealsEnvironment


_env = DealsEnvironment.from_environment()
_verify_key = VerifyKey(bytes.fromhex(_env.discord_public_key)) if _env.discord_public_key else None
logger = _env.create_logger(__name__)
metrics = Metrics(namespace="deal-dash", service="deal-interactions")


def _verify(headers: dict[str, str], body: str) -> bool:
    if _verify_key is None:
        return False
    sig = headers.get("x-signature-ed25519", "")
    ts = headers.get("x-signature-timestamp", "")
    try:
        _verify_key.verify(f"{ts}{body}".encode(), bytes.fromhex(sig))
        return True
    except (BadSignatureError, ValueError):
        return False


@metrics.log_metrics(raise_on_empty_metrics=False)
def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    body: str = event.get("body", "")

    if not _verify(headers, body):
        logger.warning("signature verification failed")
        metrics.add_metric(name="SignatureFailures", unit=MetricUnit.Count, value=1)
        return {"statusCode": 401, "body": "invalid signature"}

    data = json.loads(body)
    interaction_type: int = data["type"]
    logger.info("interaction received", extra={"type": interaction_type})
    metrics.add_metric(name="InteractionsReceived", unit=MetricUnit.Count, value=1)

    if interaction_type == 1:  # PING
        logger.info("ping acknowledged")
        return {"statusCode": 200, "body": json.dumps({"type": 1})}

    if interaction_type == 3:  # MESSAGE_COMPONENT (button)
        custom_id: str = data["data"]["custom_id"]
        action, target = custom_id.split(":", 1)
        product_key, store_key = target.split("|", 1)
        liked = action == "like"
        logger.info(
            "button pressed",
            extra={"action": action, "product_key": product_key, "store_key": store_key},
        )
        metrics.add_metric(
            name="LikeButtonPressed" if liked else "DislikeButtonPressed",
            unit=MetricUnit.Count,
            value=1,
        )

        _env.deals_table_resource.update_item(
            Key={"product_key": product_key, "store_key": store_key},
            UpdateExpression="SET #liked = :liked",
            ExpressionAttributeNames={"#liked": "liked"},
            ExpressionAttributeValues={":liked": liked},
        )
        logger.info("liked updated", extra={"product_key": product_key, "liked": liked})

        label = "👍 Liked!" if liked else "👎 Disliked!"
        response = {
            "type": 7,  # UPDATE_MESSAGE
            "data": {
                "components": [
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 3 if liked else 4,
                                "label": label,
                                "custom_id": custom_id,
                                "disabled": True,
                            }
                        ],
                    }
                ]
            },
        }
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response),
        }

    logger.warning("unknown interaction type", extra={"type": interaction_type})
    return {"statusCode": 400, "body": "unknown interaction type"}
