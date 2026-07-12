import json
from unittest.mock import MagicMock

import deal_dash.lambdas.deal_interactions.handler as _handler_module
from deal_dash.lambdas.deal_interactions.handler import handler


def _event(body: dict) -> dict:
    return {
        "headers": {"x-signature-ed25519": "sig", "x-signature-timestamp": "ts"},
        "body": json.dumps(body),
    }


def test_invalid_signature_returns_401(monkeypatch):
    monkeypatch.setattr(_handler_module, "_verify", lambda headers, body: False)
    resp = handler(_event({"type": 1}), None)
    assert resp["statusCode"] == 401


def test_malformed_signature_headers_return_401_not_crash(monkeypatch):
    from nacl.signing import SigningKey

    monkeypatch.setattr(_handler_module, "_verify_key", SigningKey.generate().verify_key)
    resp = handler({"headers": {}, "body": ""}, None)
    assert resp["statusCode"] == 401


def test_ping_acknowledged(monkeypatch):
    monkeypatch.setattr(_handler_module, "_verify", lambda headers, body: True)
    resp = handler(_event({"type": 1}), None)
    assert resp["statusCode"] == 200
    assert json.loads(resp["body"]) == {"type": 1}


def test_like_button_updates_table(monkeypatch):
    monkeypatch.setattr(_handler_module, "_verify", lambda headers, body: True)
    table = MagicMock()
    env = MagicMock()
    env.deals_table_resource = table
    monkeypatch.setattr(_handler_module, "_env", env)

    body = {
        "type": 3,
        "data": {"custom_id": "like:homedepot#123|store#5"},
    }
    resp = handler(_event(body), None)

    table.update_item.assert_called_once_with(
        Key={"product_key": "homedepot#123", "store_key": "store#5"},
        UpdateExpression="SET #liked = :liked",
        ExpressionAttributeNames={"#liked": "liked"},
        ExpressionAttributeValues={":liked": True},
    )
    assert resp["statusCode"] == 200
    payload = json.loads(resp["body"])
    button = payload["data"]["components"][0]["components"][0]
    assert button["disabled"] is True
    assert button["style"] == 3
    assert button["label"] == "👍 Liked!"


def test_dislike_button_updates_table(monkeypatch):
    monkeypatch.setattr(_handler_module, "_verify", lambda headers, body: True)
    table = MagicMock()
    env = MagicMock()
    env.deals_table_resource = table
    monkeypatch.setattr(_handler_module, "_env", env)

    body = {
        "type": 3,
        "data": {"custom_id": "dislike:homedepot#123|online"},
    }
    resp = handler(_event(body), None)

    table.update_item.assert_called_once_with(
        Key={"product_key": "homedepot#123", "store_key": "online"},
        UpdateExpression="SET #liked = :liked",
        ExpressionAttributeNames={"#liked": "liked"},
        ExpressionAttributeValues={":liked": False},
    )
    payload = json.loads(resp["body"])
    button = payload["data"]["components"][0]["components"][0]
    assert button["style"] == 4
    assert button["label"] == "👎 Disliked!"


def test_unknown_interaction_type(monkeypatch):
    monkeypatch.setattr(_handler_module, "_verify", lambda headers, body: True)
    resp = handler(_event({"type": 99}), None)
    assert resp["statusCode"] == 400
