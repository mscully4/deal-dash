import math
from collections.abc import AsyncIterator

import httpx

from deal_dash.models import Deal

_SEARCH_URL = "https://www.rebelsavings.com/api/search"
_PER_PAGE = 100


class RebelsavingsClient:
    def __init__(self, session_cookie: str) -> None:
        self._cookie = session_cookie

    async def search(
        self,
        retailer: str,
        lat: float,
        lon: float,
        radius_mi: float,
    ) -> AsyncIterator[Deal]:
        filter_by = f"stock:>0 && location_geo:({lat}, {lon}, {radius_mi:g} mi)"
        headers = {
            "Content-Type": "application/json",
            "Cookie": f"rs_session={self._cookie}",
        }
        async with httpx.AsyncClient() as http:
            page = 1
            total_pages: int | None = None
            while total_pages is None or page <= total_pages:
                payload = {
                    "retailer": retailer,
                    "sortBy": "discount:desc",
                    "filterBy": filter_by,
                    "page": page,
                    "perPage": _PER_PAGE,
                    "query": "*",
                }
                resp = await http.post(_SEARCH_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if total_pages is None:
                    found = data.get("found", 0)
                    total_pages = max(1, math.ceil(found / _PER_PAGE))
                for hit in data.get("hits", []):
                    yield Deal.from_hit(hit, retailer=retailer)
                page += 1
