from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

from deal_dash.environment import Environment


if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table


class DealsEnvironment(Environment):
    """Environment for the multi-source scraper/embedder pipeline (deal-dash-deals)."""

    deals_table: str = "deal-dash-deals"
    hc_refresh_token_secret_id: str = "deal-dash/hidden-clearances-refresh-token"

    @cached_property
    def deals_table_resource(self) -> Table:
        return self.dynamodb_resource.Table(self.deals_table)
