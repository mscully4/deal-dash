from collections.abc import AsyncIterator
from typing import Any

import httpx

from deal_dash.deals.environment import DealsEnvironment
from deal_dash.hidden_clearances.auth import refresh_access_token


_BASE_URL = "https://api.hiddenclearances.com/api/v1"
_PER_PAGE = 50


class HiddenClearancesClient:
    def __init__(self, env: DealsEnvironment | None = None) -> None:
        self._env = env or DealsEnvironment.from_environment()
        self._access_token: str | None = None

    async def _headers(self) -> dict[str, str]:
        if self._access_token is None:
            self._access_token = await refresh_access_token(env=self._env)
        return {"authorization": f"Bearer {self._access_token}"}

    async def search_feed(self, kind: str = "curated") -> AsyncIterator[dict[str, Any]]:
        """Curated/recommended feed: online deals + locked in-store leads (no store #)."""
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            page = 1
            while True:
                resp = await http.get(
                    f"{_BASE_URL}/feed",
                    params={
                        "page": page,
                        "limit": _PER_PAGE,
                        "sort": "recommended",
                        "kind": kind,
                    },
                    headers=headers,
                )
                resp.raise_for_status()
                items = resp.json().get("data", [])
                if not items:
                    return
                for item in items:
                    yield item
                if len(items) < _PER_PAGE:
                    return
                page += 1

    async def search_nearby(self, limit: int = 50) -> AsyncIterator[dict[str, Any]]:
        """Unlocked in-store clearance finds near the account's saved location (has store #)."""
        headers = await self._headers()
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                f"{_BASE_URL}/clearance/nearby",
                params={"limit": limit},
                headers=headers,
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                yield item
