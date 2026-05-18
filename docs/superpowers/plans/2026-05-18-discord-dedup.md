# Discord Notification Dedup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Suppress duplicate Discord notifications when the same UPC appears at multiple stores in a single scrape run.

**Architecture:** Module-level `dict[str, float]` in the embedder Lambda caches notified UPCs by timestamp. Before posting to Discord, check if the UPC was notified within the last 2 hours; if so, skip. Lambda instance reuse across consecutive DDB stream batches makes this reliable for the single-scraper, single-shard use case. Also fixes pre-existing broken tests caused by missing client-injection support in the handler.

**Tech Stack:** Python, pytest, aws-lambda-powertools, httpx (mocked in tests)

---

## File Map

| File | Change |
|------|--------|
| `src/deal_dash/lambdas/embedder/handler.py` | Add injection kwargs, add dedup dict + helpers, guard Discord call |
| `tests/test_embedder.py` | Fix injection calls (already correct), add dedup tests |

---

### Task 1: Add client injection to handler and restore passing tests

**Files:**
- Modify: `src/deal_dash/lambdas/embedder/handler.py`
- Test: `tests/test_embedder.py`

The four existing tests already pass `_bedrock` and `_s3vectors` as kwargs. The handler ignores them and calls `_env.bedrock_client`/`_env.s3vectors_client` directly, causing `TypeError`. Fix by accepting those kwargs and using them when provided.

- [ ] **Step 1: Run tests to confirm current failure**

```bash
uv run pytest tests/test_embedder.py -v
```

Expected: 4 FAILED with `TypeError: event_source() got an unexpected keyword argument '_bedrock'`

- [ ] **Step 2: Update handler signature to accept injectable clients**

In `src/deal_dash/lambdas/embedder/handler.py`, change the handler function signature and body:

```python
@event_source(data_class=DynamoDBStreamEvent)  # type: ignore[untyped-decorator]
def handler(
    event: DynamoDBStreamEvent,
    context: object,
    _bedrock: Any = None,
    _s3vectors: Any = None,
) -> None:
    bedrock = _bedrock if _bedrock is not None else _env.bedrock_client
    s3v = _s3vectors if _s3vectors is not None else _env.s3vectors_client
```

- [ ] **Step 3: Run tests to confirm all pass**

```bash
uv run pytest tests/test_embedder.py -v
```

Expected: 4 PASSED

- [ ] **Step 4: Commit**

```bash
git add src/deal_dash/lambdas/embedder/handler.py
git commit -m "fix: accept injectable bedrock and s3vectors clients in embedder handler"
```

---

### Task 2: Add dedup helpers to handler

**Files:**
- Modify: `src/deal_dash/lambdas/embedder/handler.py`

- [ ] **Step 1: Write failing tests for the dedup helpers**

Add to `tests/test_embedder.py`:

```python
import time
import deal_dash.lambdas.embedder.handler as _handler_module


def test_already_notified_false_for_new_upc():
    _handler_module._notified_upcs.clear()
    assert not _handler_module._already_notified("upc-new")


def test_mark_notified_then_already_notified():
    _handler_module._notified_upcs.clear()
    _handler_module._mark_notified("upc-123")
    assert _handler_module._already_notified("upc-123")


def test_already_notified_expired_entry_returns_false():
    _handler_module._notified_upcs.clear()
    _handler_module._notified_upcs["upc-old"] = time.time() - 9000  # 2.5 hours ago
    assert not _handler_module._already_notified("upc-old")


def test_already_notified_purges_stale_entries():
    _handler_module._notified_upcs.clear()
    _handler_module._notified_upcs["upc-stale"] = time.time() - 9000
    _handler_module._already_notified("upc-check")
    assert "upc-stale" not in _handler_module._notified_upcs
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_embedder.py::test_already_notified_false_for_new_upc tests/test_embedder.py::test_mark_notified_then_already_notified tests/test_embedder.py::test_already_notified_expired_entry_returns_false tests/test_embedder.py::test_already_notified_purges_stale_entries -v
```

Expected: 4 FAILED with `AttributeError: module has no attribute '_notified_upcs'`

- [ ] **Step 3: Add dedup dict and helpers to handler**

Add `import time` to the imports at the top of `src/deal_dash/lambdas/embedder/handler.py`.

After `_bot_token: str | None = None`, add:

```python
_notified_upcs: dict[str, float] = {}


def _already_notified(upc: str, ttl: int = 7200) -> bool:
    cutoff = time.time() - ttl
    stale = [k for k, t in _notified_upcs.items() if t < cutoff]
    for k in stale:
        del _notified_upcs[k]
    return upc in _notified_upcs


def _mark_notified(upc: str) -> None:
    _notified_upcs[upc] = time.time()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
uv run pytest tests/test_embedder.py::test_already_notified_false_for_new_upc tests/test_embedder.py::test_mark_notified_then_already_notified tests/test_embedder.py::test_already_notified_expired_entry_returns_false tests/test_embedder.py::test_already_notified_purges_stale_entries -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/deal_dash/lambdas/embedder/handler.py tests/test_embedder.py
git commit -m "feat: add in-memory UPC dedup helpers to embedder handler"
```

---

### Task 3: Wire dedup into the Discord notification guard

**Files:**
- Modify: `src/deal_dash/lambdas/embedder/handler.py`
- Test: `tests/test_embedder.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/test_embedder.py`:

```python
def _full_stream_record(event_name: str = "INSERT", upc: str = "012345678901", store: int = 1) -> dict:
    return {
        "eventName": event_name,
        "dynamodb": {
            "NewImage": {
                "retailer": {"S": "homedepot"},
                "upc": {"S": upc},
                "item_id": {"S": f"{upc}#{store}"},
                "title": {"S": "Padlock Steel 2in"},
                "price": {"N": "1.17"},
                "discount": {"N": "91"},
                "category": {"S": "Hardware"},
                "subcategory": {"S": "Padlocks"},
                "url": {"S": "https://homedepot.com/p/123"},
                "address": {"S": "123 Main St"},
                "city": {"S": "Columbus"},
                "state": {"S": "OH"},
            }
        },
    }


def test_handler_deduplicates_same_upc_across_stores(monkeypatch):
    from deal_dash.environment import Environment

    _handler_module._notified_upcs.clear()

    discord_calls: list[dict] = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", lambda doc: discord_calls.append(doc))
    monkeypatch.setattr(
        _handler_module,
        "_env",
        Environment(discord_bot_token_arn="arn:fake", discord_channel_id="111222333"),
    )

    vector = [0.1] * 256
    bedrock = _bedrock_mock(vector)
    s3v = MagicMock()

    handler(
        {
            "Records": [
                _full_stream_record("INSERT", upc="UPC-DUPE", store=1),
                _full_stream_record("INSERT", upc="UPC-DUPE", store=2),
                _full_stream_record("INSERT", upc="UPC-DUPE", store=3),
            ]
        },
        None,
        _bedrock=bedrock,
        _s3vectors=s3v,
    )

    assert len(discord_calls) == 1
    assert discord_calls[0]["upc"] == "UPC-DUPE"
    assert s3v.put_vectors.call_count == 3  # all 3 still embedded


def test_handler_different_upcs_each_get_discord_post(monkeypatch):
    from deal_dash.environment import Environment

    _handler_module._notified_upcs.clear()

    discord_calls: list[dict] = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", lambda doc: discord_calls.append(doc))
    monkeypatch.setattr(
        _handler_module,
        "_env",
        Environment(discord_bot_token_arn="arn:fake", discord_channel_id="111222333"),
    )

    vector = [0.1] * 256
    bedrock = _bedrock_mock(vector)
    s3v = MagicMock()

    handler(
        {
            "Records": [
                _full_stream_record("INSERT", upc="UPC-AAA", store=1),
                _full_stream_record("INSERT", upc="UPC-BBB", store=1),
            ]
        },
        None,
        _bedrock=bedrock,
        _s3vectors=s3v,
    )

    assert len(discord_calls) == 2
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_embedder.py::test_handler_deduplicates_same_upc_across_stores tests/test_embedder.py::test_handler_different_upcs_each_get_discord_post -v
```

Expected: FAILED — `test_deduplicates` fails because handler posts 3 times instead of 1; `test_different_upcs` may pass or fail depending on current code.

- [ ] **Step 3: Update Discord guard in handler to use dedup**

In `src/deal_dash/lambdas/embedder/handler.py`, replace the existing Discord guard block:

```python
        if (
            _env.discord_bot_token_arn
            and _env.discord_channel_id
            and event_name == DynamoDBRecordEventName.INSERT
            and retailer in _NOTIFY_RETAILERS
        ):
            _post_to_discord(doc)
```

With:

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

- [ ] **Step 4: Run all embedder tests**

```bash
uv run pytest tests/test_embedder.py -v
```

Expected: all PASSED (original 4 + 4 dedup helpers + 2 integration = 10 total)

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all PASSED

- [ ] **Step 6: Lint and type check**

```bash
uv run ruff check && uv run mypy src
```

Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/deal_dash/lambdas/embedder/handler.py tests/test_embedder.py
git commit -m "feat: deduplicate Discord notifications by UPC using in-memory cache"
```
