from __future__ import annotations

import json
import os
from typing import Any

import boto3
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")
_VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET", "deal-dash-vectors")
_VECTOR_INDEX = os.environ.get("VECTOR_INDEX", "deals")
_REGION = os.environ.get("AWS_REGION", "us-east-2")

_verify_key = VerifyKey(bytes.fromhex(_PUBLIC_KEY)) if _PUBLIC_KEY else None
_s3vectors = boto3.client("s3vectors", region_name=_REGION)


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


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
    body: str = event.get("body", "")

    if not _verify(headers, body):
        return {"statusCode": 401, "body": "invalid signature"}

    data = json.loads(body)

    if data["type"] == 1:  # PING
        return {"statusCode": 200, "body": json.dumps({"type": 1})}

    if data["type"] == 3:  # MESSAGE_COMPONENT (button)
        custom_id: str = data["data"]["custom_id"]
        action, upc = custom_id.split(":", 1)
        liked = action == "like"

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

    return {"statusCode": 400, "body": "unknown interaction type"}
