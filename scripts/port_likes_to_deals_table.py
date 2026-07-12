#!/usr/bin/env python3
"""
Port liked/disliked status from the old S3 Vectors bucket (keyed by UPC,
single-source/rebelsavings-only) onto the new deal-dash-deals table
(keyed by product_key/store_key). Joins on the `upc` attribute, which
only Rebel Savings-sourced rows have — Hidden Clearances rows have no
UPC and are untouched by this script.
"""
from collections import defaultdict

import boto3


_REGION = "us-east-2"
_DEALS_TABLE = "deal-dash-deals"
_VECTOR_BUCKET = "deal-dash-vectors"
_VECTOR_INDEX = "deals"

session = boto3.Session(profile_name="default", region_name=_REGION)
ddb = session.resource("dynamodb")
s3v = session.client("s3vectors")
table = ddb.Table(_DEALS_TABLE)


def list_old_likes() -> dict[str, bool]:
    """Return {upc: liked} from the old S3 Vectors metadata."""
    likes: dict[str, bool] = {}
    next_token = None
    while True:
        kwargs: dict = {
            "vectorBucketName": _VECTOR_BUCKET,
            "indexName": _VECTOR_INDEX,
            "returnMetadata": True,
            "returnData": False,
        }
        if next_token:
            kwargs["nextToken"] = next_token
        resp = s3v.list_vectors(**kwargs)
        for v in resp.get("vectors", []):
            metadata = v.get("metadata", {})
            if "liked" in metadata:
                likes[v["key"]] = metadata["liked"]
        next_token = resp.get("nextToken")
        if not next_token:
            break
    return likes


def scan_upc_index() -> dict[str, list[tuple[str, str]]]:
    """Return {upc: [(product_key, store_key), ...]} for the new table."""
    index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    kwargs: dict = {"ProjectionExpression": "upc, product_key, store_key"}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            upc = item.get("upc")
            if upc:
                index[upc].append((item["product_key"], item["store_key"]))
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return index


def port(likes: dict[str, bool], upc_index: dict[str, list[tuple[str, str]]]) -> None:
    matched_upcs = 0
    unmatched_upcs = 0
    rows_updated = 0

    for upc, liked in likes.items():
        rows = upc_index.get(upc, [])
        if not rows:
            unmatched_upcs += 1
            continue
        matched_upcs += 1
        for product_key, store_key in rows:
            table.update_item(
                Key={"product_key": product_key, "store_key": store_key},
                UpdateExpression="SET #liked = :liked",
                ExpressionAttributeNames={"#liked": "liked"},
                ExpressionAttributeValues={":liked": liked},
            )
            rows_updated += 1

    print(
        f"done. old_likes={len(likes)} matched_upcs={matched_upcs} "
        f"unmatched_upcs={unmatched_upcs} rows_updated={rows_updated}"
    )


if __name__ == "__main__":
    print("listing old S3 Vectors likes...")
    likes = list_old_likes()
    print(f"found {len(likes)} liked/disliked entries")

    print("scanning new deals table...")
    upc_index = scan_upc_index()
    print(f"found {len(upc_index)} unique UPCs in deal-dash-deals")

    port(likes, upc_index)
