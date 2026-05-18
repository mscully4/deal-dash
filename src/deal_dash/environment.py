from __future__ import annotations

import json
import logging
import os
from enum import Enum
from functools import cached_property
from typing import TYPE_CHECKING, Mapping, Self, cast

import boto3
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined


if TYPE_CHECKING:
    from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
    from mypy_boto3_dynamodb import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table
    from mypy_boto3_s3vectors import S3VectorsClient
    from mypy_boto3_secretsmanager import SecretsManagerClient


_STANDARD_LOG_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


def _json_default(obj: object) -> object:
    if isinstance(obj, Enum):
        return obj.name
    return str(obj)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD_LOG_ATTRS}
        payload.update(extras)
        return json.dumps(payload, default=_json_default)


def _get_default_or_mapping_item(*, key: str, field: FieldInfo, env: Mapping[str, str]) -> str:
    if val := env.get(key.upper()):
        return val
    elif field.default is not PydanticUndefined:
        return cast(str, field.default)
    raise RuntimeError(f"Field '{key}' not present in env map")


class Environment(BaseModel):
    model_config = {"frozen": True}

    aws_region: str = "us-east-2"
    rebel_savings_deals_table: str = "rebel-savings-deals"
    vector_bucket: str = "deal-dash-vectors"
    vector_index: str = "deals"
    discord_bot_token_arn: str = ""
    discord_channel_id: str = ""

    @classmethod
    def from_environment(cls, env: dict[str, str] = dict(os.environ)) -> Self:
        args = {}
        for key, field in cls.model_fields.items():
            args[key] = _get_default_or_mapping_item(key=key, field=field, env=env)
        return cls(**args)

    @cached_property
    def boto3_session(self) -> boto3.Session:
        return boto3.Session(region_name=self.aws_region)

    @cached_property
    def dynamodb_resource(self) -> DynamoDBServiceResource:
        return self.boto3_session.resource("dynamodb")

    @cached_property
    def deals_table_resource(self) -> Table:
        return self.dynamodb_resource.Table(self.rebel_savings_deals_table)

    @cached_property
    def bedrock_client(self) -> BedrockRuntimeClient:
        return self.boto3_session.client("bedrock-runtime")

    @cached_property
    def s3vectors_client(self) -> S3VectorsClient:
        return self.boto3_session.client("s3vectors")

    @cached_property
    def secrets_manager_client(self) -> SecretsManagerClient:
        return self.boto3_session.client("secretsmanager")

    def create_logger(self, name: str, level: int = logging.INFO) -> logging.Logger:
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(_JsonFormatter())
            logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
        return logger
