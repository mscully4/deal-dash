from __future__ import annotations

import json
import os
from typing import Any

import boto3
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey


_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")
_TABLE_NAME = os.environ.get("DEALS_TABLE", "rebel-savings-deals")
_REGION = os.environ.get("AWS_REGION", "us-east-2")

_verify_key = VerifyKey(bytes.fromhex(_PUBLIC_KEY)) if _PUBLIC_KEY else None
_dynamodb = boto3.resource("dynamodb", region_name=_REGION)
_table = _dynamodb.Table(_TABLE_NAME)


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
        action, retailer, item_id = custom_id.split(":", 2)
        liked = action == "like"

        _table.update_item(
            Key={"retailer": retailer, "item_id": item_id},
            UpdateExpression="SET liked = :val",
            ExpressionAttributeValues={":val": liked},
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
