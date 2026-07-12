#!/usr/bin/env python3
"""
Backfill title into S3 Vector metadata for existing vectors.
Scans DynamoDB for all deals, then for each UPC that has a vector
without a title in metadata, updates the vector metadata in-place
(no re-embedding — same float32 data, just metadata patched).
"""

import boto3


_REGION = "us-east-2"
_TABLE = "rebel-savings-deals"
_VECTOR_BUCKET = "deal-dash-vectors"
_VECTOR_INDEX = "deals"

session = boto3.Session(profile_name="default", region_name=_REGION)
ddb = session.resource("dynamodb")
s3v = session.client("s3vectors")
table = ddb.Table(_TABLE)


def scan_upc_titles() -> dict[str, str]:
    """Return {upc: title} — last-write wins if multiple items share a UPC."""
    upc_titles: dict[str, str] = {}
    kwargs: dict = {"ProjectionExpression": "upc, title"}
    while True:
        resp = table.scan(**kwargs)
        for item in resp.get("Items", []):
            upc = item.get("upc")
            title = item.get("title")
            if upc and title:
                upc_titles[upc] = title
        last = resp.get("LastEvaluatedKey")
        if not last:
            break
        kwargs["ExclusiveStartKey"] = last
    return upc_titles


def backfill(upc_titles: dict[str, str]) -> None:
    upcs = list(upc_titles.keys())
    total = len(upcs)
    updated = 0
    skipped_no_vector = 0
    skipped_has_title = 0

    # get_vectors accepts up to 100 keys at a time
    batch_size = 100
    for i in range(0, total, batch_size):
        batch = upcs[i : i + batch_size]
        resp = s3v.get_vectors(
            vectorBucketName=_VECTOR_BUCKET,
            indexName=_VECTOR_INDEX,
            keys=batch,
            returnData=True,
            returnMetadata=True,
        )
        vectors = {v["key"]: v for v in resp.get("vectors", [])}

        to_put = []
        for upc in batch:
            if upc not in vectors:
                skipped_no_vector += 1
                continue
            vec = vectors[upc]
            metadata = vec.get("metadata", {})
            if "title" in metadata:
                skipped_has_title += 1
                continue
            metadata["title"] = upc_titles[upc]
            to_put.append({
                "key": upc,
                "data": vec["data"],
                "metadata": metadata,
            })

        if to_put:
            s3v.put_vectors(
                vectorBucketName=_VECTOR_BUCKET,
                indexName=_VECTOR_INDEX,
                vectors=to_put,
            )
            updated += len(to_put)
            print(f"  updated {updated}/{total} ...", end="\r", flush=True)

    print(f"\ndone. updated={updated}  skipped_no_vector={skipped_no_vector}  skipped_has_title={skipped_has_title}")


if __name__ == "__main__":
    print("scanning DynamoDB...")
    upc_titles = scan_upc_titles()
    print(f"found {len(upc_titles)} unique UPCs")
    backfill(upc_titles)
