import os
from functools import cached_property
from typing import Mapping, Self, cast

import boto3
from mypy_boto3_bedrock_runtime import BedrockRuntimeClient
from mypy_boto3_dynamodb import DynamoDBServiceResource
from mypy_boto3_dynamodb.service_resource import Table
from mypy_boto3_s3vectors import S3VectorsClient
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined


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
