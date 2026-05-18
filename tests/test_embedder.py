import json
import time
from unittest.mock import MagicMock

import deal_dash.lambdas.embedder.handler as _handler_module
from deal_dash.lambdas.embedder.handler import handler


def _stream_record(event_name: str = "INSERT", upc: str = "012345678901") -> dict:
    return {
        "eventName": event_name,
        "dynamodb": {
            "NewImage": {
                "retailer": {"S": "homedepot"},
                "upc": {"S": upc},
                "title": {"S": "Padlock Steel 2in"},
                "price": {"N": "1.17"},
                "discount": {"N": "91"},
                "category": {"S": "Hardware"},
                "subcategory": {"S": "Padlocks"},
            }
        },
    }


def _full_stream_record(
    event_name: str = "INSERT", upc: str = "012345678901", store: int = 1
) -> dict:
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


def _make_env(
    vector: list[float] | None = None,
    *,
    discord_bot_token_arn: str = "",
    discord_channel_id: str = "",
) -> tuple[MagicMock, MagicMock]:
    """Returns (env_mock, s3v_mock). bedrock returns `vector` on invoke_model."""
    bedrock = MagicMock()
    if vector is not None:
        body = MagicMock()
        body.read.return_value = json.dumps({"embedding": vector}).encode()
        bedrock.invoke_model.return_value = {"body": body}

    s3v = MagicMock()
    s3v.get_vectors.return_value = {"vectors": []}

    env = MagicMock()
    env.bedrock_client = bedrock
    env.s3vectors_client = s3v
    env.vector_bucket = "deal-dash-vectors"
    env.vector_index = "deals"
    env.discord_bot_token_arn = discord_bot_token_arn
    env.discord_channel_id = discord_channel_id
    return env, s3v


def test_handler_skips_delete(monkeypatch):
    env, s3v = _make_env()
    monkeypatch.setattr(_handler_module, "_env", env)
    handler({"Records": [_stream_record("REMOVE")]}, None)
    env.bedrock_client.invoke_model.assert_not_called()
    s3v.put_vectors.assert_not_called()


def test_handler_embeds_and_stores_on_insert(monkeypatch):
    vector = [0.1] * 256
    env, s3v = _make_env(vector)
    monkeypatch.setattr(_handler_module, "_env", env)

    handler({"Records": [_stream_record("INSERT")]}, None)

    env.bedrock_client.invoke_model.assert_called_once()
    call_kw = env.bedrock_client.invoke_model.call_args.kwargs
    assert call_kw["modelId"] == "amazon.titan-embed-text-v2:0"
    body = json.loads(call_kw["body"])
    assert body["inputText"] == "Padlock Steel 2in Hardware Padlocks"
    assert body["dimensions"] == 256

    s3v.put_vectors.assert_called_once()
    kw = s3v.put_vectors.call_args.kwargs
    assert kw["vectorBucketName"] == "deal-dash-vectors"
    assert kw["indexName"] == "deals"
    vec = kw["vectors"][0]
    assert vec["key"] == "012345678901"
    assert vec["data"]["float32"] == vector
    assert vec["metadata"]["retailer"] == "homedepot"
    assert vec["metadata"]["discount"] == 91
    assert vec["metadata"]["price"] == 1.17
    assert "liked" not in vec["metadata"]


def test_handler_embeds_on_modify(monkeypatch):
    env, s3v = _make_env([0.2] * 256)
    monkeypatch.setattr(_handler_module, "_env", env)

    handler({"Records": [_stream_record("MODIFY")]}, None)

    env.bedrock_client.invoke_model.assert_called_once()
    s3v.get_vectors.assert_called_once()
    s3v.put_vectors.assert_called_once()


def test_handler_modify_preserves_liked(monkeypatch):
    env, s3v = _make_env([0.2] * 256)
    s3v.get_vectors.return_value = {
        "vectors": [{"metadata": {"retailer": "homedepot", "liked": True}}]
    }
    monkeypatch.setattr(_handler_module, "_env", env)

    handler({"Records": [_stream_record("MODIFY")]}, None)

    kw = s3v.put_vectors.call_args.kwargs
    assert kw["vectors"][0]["metadata"]["liked"] is True


def test_handler_processes_multiple_records(monkeypatch):
    env, s3v = _make_env([0.1] * 256)
    monkeypatch.setattr(_handler_module, "_env", env)

    handler(
        {"Records": [_stream_record("INSERT", "aaa111"), _stream_record("INSERT", "bbb222")]},
        None,
    )

    assert env.bedrock_client.invoke_model.call_count == 2
    assert s3v.put_vectors.call_count == 2


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


def test_handler_deduplicates_same_upc_across_stores(monkeypatch):
    _handler_module._notified_upcs.clear()
    discord_calls: list[dict] = []
    env, s3v = _make_env([0.1] * 256, discord_bot_token_arn="arn:fake", discord_channel_id="111222333")
    monkeypatch.setattr(_handler_module, "_post_to_discord", lambda doc: discord_calls.append(doc))
    monkeypatch.setattr(_handler_module, "_env", env)

    handler(
        {
            "Records": [
                _full_stream_record("INSERT", upc="UPC-DUPE", store=1),
                _full_stream_record("INSERT", upc="UPC-DUPE", store=2),
                _full_stream_record("INSERT", upc="UPC-DUPE", store=3),
            ]
        },
        None,
    )

    assert len(discord_calls) == 1
    assert discord_calls[0]["upc"] == "UPC-DUPE"
    assert s3v.put_vectors.call_count == 3


def test_handler_different_upcs_each_get_discord_post(monkeypatch):
    _handler_module._notified_upcs.clear()
    discord_calls: list[dict] = []
    env, s3v = _make_env([0.1] * 256, discord_bot_token_arn="arn:fake", discord_channel_id="111222333")
    monkeypatch.setattr(_handler_module, "_post_to_discord", lambda doc: discord_calls.append(doc))
    monkeypatch.setattr(_handler_module, "_env", env)

    handler(
        {
            "Records": [
                _full_stream_record("INSERT", upc="UPC-AAA", store=1),
                _full_stream_record("INSERT", upc="UPC-BBB", store=1),
            ]
        },
        None,
    )

    assert len(discord_calls) == 2
