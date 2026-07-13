import time
from unittest.mock import MagicMock

import deal_dash.lambdas.notifier.handler as _handler_module
from deal_dash.lambdas.notifier.handler import handler


def _stream_record(
    event_name: str = "INSERT",
    product_key: str = "homedepot#330884657",
    price: str = "29.99",
    retailer: str = "homedepot",
    **extra: str,
) -> dict:
    image = {
        "product_key": {"S": product_key},
        "store_key": {"S": "store#509"},
        "retailer": {"S": retailer},
        "title": {"S": "Milwaukee PACKOUT Rack Kit"},
        "price": {"N": price},
        "discount": {"N": "60"},
        "category": {"S": "Garage"},
    }
    for k, v in extra.items():
        image[k] = {"S": v}
    return {"eventName": event_name, "dynamodb": {"NewImage": image}}


def _record_call(calls: list) -> object:
    def _fake_post(doc: dict) -> bool:
        calls.append(doc)
        return True

    return _fake_post


def _make_env(
    *, discord_bot_token_arn: str = "arn:fake", discord_channel_id: str = "111"
) -> MagicMock:
    env = MagicMock()
    env.discord_bot_token_arn = discord_bot_token_arn
    env.discord_channel_id = discord_channel_id
    return env


def test_handler_skips_non_insert(monkeypatch):
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))
    handler({"Records": [_stream_record("MODIFY")]}, None)
    assert calls == []


def test_handler_posts_on_insert(monkeypatch):
    _handler_module._notified_products.clear()
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))
    handler({"Records": [_stream_record()]}, None)
    assert len(calls) == 1
    assert calls[0]["product_key"] == "homedepot#330884657"


def test_handler_skips_sparse_item_from_like_upsert(monkeypatch):
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))
    sparse_record = {
        "eventName": "INSERT",
        "dynamodb": {
            "NewImage": {
                "product_key": {"S": "homedepot#stale-button-click"},
                "store_key": {"S": "store#509"},
                "liked": {"BOOL": True},
            }
        },
    }
    handler({"Records": [sparse_record]}, None)
    assert calls == []


def test_handler_skips_no_discord_config(monkeypatch):
    env = _make_env(discord_bot_token_arn="", discord_channel_id="")
    monkeypatch.setattr(_handler_module, "_env", env)
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))
    handler({"Records": [_stream_record()]}, None)
    assert calls == []


def test_handler_skips_retailer_not_in_allowlist(monkeypatch):
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))
    handler({"Records": [_stream_record(retailer="tractorsupply")]}, None)
    assert calls == []


def test_handler_skips_low_price(monkeypatch):
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))
    handler({"Records": [_stream_record(price="4.99")]}, None)
    assert calls == []


def test_handler_dedupes_same_product_key_across_stores(monkeypatch):
    _handler_module._notified_products.clear()
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))

    handler(
        {
            "Records": [
                _stream_record(product_key="homedepot#330884657"),
                _stream_record(product_key="homedepot#330884657"),
            ]
        },
        None,
    )
    assert len(calls) == 1


def test_handler_different_products_each_notify(monkeypatch):
    _handler_module._notified_products.clear()
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    calls = []
    monkeypatch.setattr(_handler_module, "_post_to_discord", _record_call(calls))

    handler(
        {
            "Records": [
                _stream_record(product_key="homedepot#111"),
                _stream_record(product_key="homedepot#222"),
            ]
        },
        None,
    )
    assert len(calls) == 2


def test_post_to_discord_includes_like_dislike_buttons(monkeypatch):
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    monkeypatch.setattr(_handler_module, "_get_bot_token", lambda: "fake-token")

    resp = MagicMock()
    resp.status_code = 200
    posted = MagicMock(return_value=resp)
    monkeypatch.setattr(_handler_module.httpx, "post", posted)

    doc = {
        "product_key": "homedepot#330884657",
        "store_key": "store#509",
        "retailer": "homedepot",
        "title": "Milwaukee PACKOUT Rack Kit",
        "price": "29.99",
        "discount": "60",
        "category": "Garage",
    }
    assert _handler_module._post_to_discord(doc) is True

    payload = posted.call_args.kwargs["json"]
    buttons = payload["components"][0]["components"]
    assert buttons[0]["custom_id"] == "like:homedepot#330884657|store#509"
    assert buttons[1]["custom_id"] == "dislike:homedepot#330884657|store#509"


def test_rate_limited_post_is_skipped_not_marked_notified(monkeypatch):
    _handler_module._notified_products.clear()
    monkeypatch.setattr(_handler_module, "_env", _make_env())
    monkeypatch.setattr(_handler_module, "_get_bot_token", lambda: "fake-token")

    resp = MagicMock()
    resp.status_code = 429
    monkeypatch.setattr(
        _handler_module.httpx, "post", MagicMock(return_value=resp)
    )

    handler({"Records": [_stream_record(product_key="homedepot#rate-limited")]}, None)

    assert not _handler_module._already_notified("homedepot#rate-limited")


def test_already_notified_false_for_new_key():
    _handler_module._notified_products.clear()
    assert not _handler_module._already_notified("homedepot#new")


def test_already_notified_expired_entry_returns_false():
    _handler_module._notified_products.clear()
    _handler_module._notified_products["homedepot#old"] = time.time() - 9000
    assert not _handler_module._already_notified("homedepot#old")
