from __future__ import annotations

import json
import os
from typing import Any

import boto3
from aws_lambda_powertools import Logger
from aws_lambda_powertools.metrics import Metrics, MetricUnit
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")
_VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET", "deal-dash-vectors")
_VECTOR_INDEX = os.environ.get("VECTOR_INDEX", "deals")
_REGION = os.environ.get("AWS_REGION", "us-east-2")

_verify_key = VerifyKey(bytes.fromhex(_PUBLIC_KEY)) if _PUBLIC_KEY else None
_s3vectors = boto3.client("s3vectors", region_name=_REGION)
logger = Logger(service=__name__)
metrics = Metrics(namespace="deal-dash", service="discord-handler")


def _verify(headers: dict[str, str], body: str) -> bool:
    if _verify_key is None:
        return False
    sig = headers.get("x-signature-ed25519", "")
    ts = headers.get("x-signature-timestamp", "")
    try:
        _verify_key.verify(f"{ts}{body}".encode(), bytes.fromhex(sig))
        return True
    except BadSignatureError:
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
        action, upc = custom_id.split(":", 1)
        liked = action == "like"
        logger.info("button pressed", extra={"action": action, "upc": upc})
        metrics.add_metric(
            name="LikeButtonPressed" if liked else "DislikeButtonPressed",
            unit=MetricUnit.Count,
            value=1,
        )

        resp = _s3vectors.get_vectors(
            vectorBucketName=_VECTOR_BUCKET,
            indexName=_VECTOR_INDEX,
            keys=[upc],
            returnData=True,
            returnMetadata=True,
        )
        vectors = resp.get("vectors", [])
        if vectors:
            vec = vectors[0]
            updated_metadata = {**vec.get("metadata", {}), "liked": liked}
            _s3vectors.put_vectors(
                vectorBucketName=_VECTOR_BUCKET,
                indexName=_VECTOR_INDEX,
                vectors=[{"key": upc, "data": vec["data"], "metadata": updated_metadata}],
            )
            logger.info("liked updated", extra={"upc": upc, "liked": liked})
        else:
            logger.warning("vector not found for upc", extra={"upc": upc})

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
