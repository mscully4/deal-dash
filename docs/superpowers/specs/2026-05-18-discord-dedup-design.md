# Discord Notification Dedup

## Problem

Same product (same UPC) appears at multiple Home Depot stores. Each store is a separate DynamoDB record (`item_id = f"{upc}#{store}"`), so a new clearance item at 5 stores produces 5 INSERT events → 5 Discord posts.

Notifications fire on INSERT only (not MODIFY), so dedup only matters when a UPC first enters the system across multiple stores simultaneously.

## Decision

Module-level in-memory cache in the embedder Lambda. Zero new infrastructure.

**Rationale:** DynamoDB streams deliver one shard per partition. All `homedepot` records flow through one shard, processed sequentially. Lambda instances are reused (warm) between consecutive invocations, so a module-level dict persists across batches from the same scrape run. No extra AWS calls, no new tables, no CDK changes.

**Accepted limitation:** Lambda cold start or scale-out resets/splits the cache, which could produce a duplicate Discord post. Acceptable for a personal low-volume tool.

## Design

### Cache structure

```python
_notified_upcs: dict[str, float] = {}  # upc -> epoch timestamp
```

Module-level in `handler.py`. Persists across invocations on a warm Lambda instance.

### Helper functions

```python
def _already_notified(upc: str, ttl: int = 7200) -> bool:
    cutoff = time.time() - ttl
    stale = [k for k, t in _notified_upcs.items() if t < cutoff]
    for k in stale:
        del _notified_upcs[k]
    return upc in _notified_upcs

def _mark_notified(upc: str) -> None:
    _notified_upcs[upc] = time.time()
```

TTL of 7200s (2h). Stale entries purged on each check to prevent unbounded growth.

### Integration point

In `handler.py`, guard the `_post_to_discord` call:

```python
if (
    _env.discord_bot_token_arn
    and _env.discord_channel_id
    and event_name == DynamoDBRecordEventName.INSERT
    and retailer in _NOTIFY_RETAILERS
    and not _already_notified(upc)
):
    _post_to_discord(doc)
    _mark_notified(upc)
```

## Scope

- **Changed:** `src/deal_dash/lambdas/embedder/handler.py`
- **Unchanged:** CDK stack, scraper, discord_handler, DynamoDB schema, S3 Vectors

## Future escape hatch

If duplicate posts become a real issue (scale-out, frequent cold starts), replace the in-memory dict with a DynamoDB conditional write on a `deal-dash-discord-dedup` table (PK: `upc`, TTL: `expires_at`). The interface (`_already_notified` / `_mark_notified`) stays the same — swap the implementation.
