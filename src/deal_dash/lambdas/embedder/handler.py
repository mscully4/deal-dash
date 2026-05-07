import json
import os
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer


_VECTOR_BUCKET = os.environ.get("VECTOR_BUCKET_NAME", "deal-dash-vectors")
_VECTOR_INDEX = os.environ.get("VECTOR_INDEX_NAME", "deals")
_MODEL_ID = "amazon.titan-embed-text-v2:0"
_DIMENSIONS = 256

_deserializer = TypeDeserializer()


def _deserialize(image: dict[str, Any]) -> dict[str, Any]:
    return {k: _deserializer.deserialize(v) for k, v in image.items()}


def _embed(text: str, bedrock: Any) -> list[float]:
    body = json.dumps({"inputText": text, "dimensions": _DIMENSIONS, "normalize": True})
    resp = bedrock.invoke_model(modelId=_MODEL_ID, body=body)
    return list(json.loads(resp["body"].read())["embedding"])


def handler(
    event: dict[str, Any],
    context: object,
    *,
    _bedrock: Any = None,
    _s3vectors: Any = None,
) -> None:
    bedrock = _bedrock or boto3.client("bedrock-runtime")
    s3v = _s3vectors or boto3.client("s3vectors")

    for record in event["Records"]:
        if record["eventName"] not in ("INSERT", "MODIFY"):
            continue
        doc = _deserialize(record["dynamodb"]["NewImage"])
        text = f"{doc['title']} {doc['category']} {doc.get('subcategory', '')}"
        vector = _embed(text, bedrock)
        metadata: dict[str, Any] = {
            "retailer": doc["retailer"],
            "category": doc["category"],
            "discount": int(doc["discount"]),
            "price": float(doc["price"]),
        }
        liked = doc.get("liked")
        if isinstance(liked, bool):
            metadata["liked"] = liked
        s3v.put_vectors(
            vectorBucketName=_VECTOR_BUCKET,
            indexName=_VECTOR_INDEX,
            vectors=[{"key": doc["upc"], "data": {"float32": vector}, "metadata": metadata}],
        )
