# Vector Embedding Pipeline for Deal Similarity

**Date:** 2026-05-07
**Status:** Approved

## Overview

Embed deal information using Amazon Bedrock Titan Embeddings and store vectors in an S3 Vector bucket. Enables nearest-neighbor similarity search to power future personalization (learn which deals the user likes). Embedding is triggered automatically when deals land in DynamoDB via Streams.

Scraper (CLI) remains local for now — not in scope. DynamoDB is the source of truth; embedding fires regardless of write source.

---

## Architecture

```
DynamoDB (rebel-savings-deals)
  │  [Streams — INSERT/MODIFY]
  ▼
EmbedderLambda (Python 3.12)
  │  embed text → Bedrock Titan Embeddings V2 (256-dim)
  │  store vector + metadata → S3 Vectors
  ▼
Vector Bucket: deal-dash-vectors
  └── Index: deals
        key: item_id (upc#store)
        vector: float32, 256-dim, cosine distance
        metadata: retailer, category, discount, price
```

**Future query flow (not in scope — Discord bot):**
```
User preference profile (mean of liked deal vectors)
  → QueryVectors(top_k=20, filter: retailer=X, discount>=N)
  → re-rank current search results or surface stored deals
```

---

## Infrastructure (CDK — RebelSavingsStack)

Three additions to the existing `RebelSavingsStack`:

### 1. DynamoDB Streams

Enable `NEW_IMAGE` stream on the existing `rebel-savings-deals` table.

### 2. S3 Vector Bucket + Index

No L2 CDK constructs exist for S3 Vectors yet — use `CfnResource`:

| Resource | Config |
|---|---|
| Vector bucket | `deal-dash-vectors` |
| Vector index | `deals` |
| Data type | `float32` |
| Dimensions | `256` |
| Distance metric | `cosine` |

### 3. EmbedderLambda

- **Code:** `src/deal_dash/lambdas/embedder/handler.py`
- **Runtime:** Python 3.12, zip deployment (no Playwright — small deps, boto3 only)
- **Event source:** DynamoDB Streams on `rebel-savings-deals`
- **Batch size:** 10 records, bisect-on-error enabled
- **IAM permissions:**
  - `bedrock:InvokeModel` on `amazon.titan-embed-text-v2:0`
  - `s3vectors:PutVectors` on `deal-dash-vectors/deals`
  - `dynamodb:GetRecords`, `dynamodb:GetShardIterator`, `dynamodb:DescribeStream`, `dynamodb:ListStreams` on the table stream

---

## Embedder Lambda Logic

**Text to embed:** `"{title} {category} {subcategory}"` — semantic content only. Retailer, discount, and price go in metadata for filtering, not in the vector.

**Embedding model:** `amazon.titan-embed-text-v2:0`, dimension=256. Chosen for Lambda fit: smallest supported dimension, fast, no model bundling required.

```python
for record in event["Records"]:
    if record["eventName"] not in ("INSERT", "MODIFY"):
        continue
    doc = deserialize(record["dynamodb"]["NewImage"])
    text = f"{doc['title']} {doc['category']} {doc['subcategory']}"
    vector = bedrock_embed(text, dimensions=256)
    s3vectors_client.put_vectors(
        vectorBucketName="deal-dash-vectors",
        vectorIndexName="deals",
        vectors=[{
            "key": doc["item_id"],           # upc#store
            "data": {"float32": vector},
            "metadata": {
                "retailer": doc["retailer"],
                "category": doc["category"],
                "discount": int(doc["discount"]),
                "price": float(doc["price"]),
            },
        }],
    )
```

**MODIFY events:** `PutVectors` is idempotent by key — re-embeds and overwrites cleanly if deal data changes.

---

## Vector Schema

| Field | Type | Purpose |
|---|---|---|
| `key` | string | `{upc}#{store}` — matches DynamoDB SK |
| `data` | float32[256] | Semantic embedding of title + category + subcategory |
| `retailer` | string (metadata) | Filter by retailer at query time |
| `category` | string (metadata) | Filter or display |
| `discount` | number (metadata) | Filter by minimum discount |
| `price` | number (metadata) | Display / range filter |

---

## Error Handling

- **Bedrock throttling:** boto3 retry config handles exponential backoff automatically.
- **Stream failures:** Lambda bisects the batch on error (`BisectBatchOnFunctionError=true`) — isolates bad records rather than blocking the stream.
- **Missing fields:** Lambda raises on unexpected DynamoDB schema — surfaces in CloudWatch, does not silently swallow.
- **DELETE events:** ignored — vectors persist in S3 Vectors after deal deleted from DynamoDB (intentional: historical embedding for preference learning).

---

## Testing

**Unit tests:** mock boto3 clients (Bedrock + S3 Vectors), assert:
- correct text construction from deal fields
- correct vector key (`item_id`)
- metadata values match deal fields
- DELETE records are skipped

**Integration:** S3 Vectors has no local emulator — test against real AWS (dev stage). Not part of local test suite.

**Manual smoke test:**
```bash
# After CLI writes a deal to DynamoDB:
aws s3vectors get-vector \
  --vector-bucket-name deal-dash-vectors \
  --vector-index-name deals \
  --key "<upc>#<store>"
```

---

## Prerequisites

- **DynamoDB writes from scraper:** `RebelsavingsClient` currently prints deals to terminal only — it must be extended to write deals to `rebel-savings-deals` before the embedding pipeline fires. This is a hard dependency but a separate implementation task.

---

## Out of Scope

- Scraper Lambda (stay local for now)
- Feedback signal / user preference profile (Discord bot, future)
- Query flow / re-ranking (future)
- Session cookie caching
