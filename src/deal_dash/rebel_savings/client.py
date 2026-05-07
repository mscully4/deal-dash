import math
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import httpx

from deal_dash.rebel_savings.models import Deal
from deal_dash.rebel_savings.session import get_session_cookie

_SEARCH_URL = "https://www.rebelsavings.com/api/search"
_PER_PAGE = 100
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# Maps CLI retailer name → (API code, site path for Referer header)
_RETAILER_META: dict[str, tuple[str, str]] = {
    "homedepot": ("hd", "home-depot"),
    "lowes": ("lowes", "lowes"),
    "walmart": ("walmart", "walmart"),
    "walgreens": ("walgreens", "walgreens"),
    "tractorsupply": ("tsc", "tractor-supply"),
}


class RebelsavingsClient:
    def __init__(self) -> None:
        self._cookie: str | None = None

    async def _search_pages(
        self,
        retailer: str,
        lat: float,
        lon: float,
        radius_mi: float,
        since_ts: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if self._cookie is None:
            self._cookie = await get_session_cookie(retailer)
        api_code, site_path = _RETAILER_META.get(retailer, (retailer, retailer))
        filter_by = f"stock:>0 && location_geo:({lat}, {lon}, {radius_mi:g} mi)"
        if since_ts is not None:
            filter_by += f" && dateAdded:>{since_ts}"
        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9",
            "content-type": "application/json",
            "origin": "https://www.rebelsavings.com",
            "priority": "u=1, i",
            "referer": f"https://www.rebelsavings.com/{site_path}/",
            "sec-ch-ua": '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": _USER_AGENT,
            "Cookie": f"rs_session={self._cookie}",
        }
        async with httpx.AsyncClient() as http:
            page = 1
            total_pages: int | None = None
            while total_pages is None or page <= total_pages:
                payload = {
                    "retailer": api_code,
                    "sortBy": "dateAdded:desc",
                    "filterBy": filter_by,
                    "page": page,
                    "perPage": _PER_PAGE,
                    "query": "*",
                    "groupBy": "title",
                }
                resp = await http.post(_SEARCH_URL, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                if total_pages is None:
                    found = data.get("found", 0)
                    total_pages = max(1, math.ceil(found / _PER_PAGE))
                yield data
                page += 1

    async def search(
        self,
        retailer: str,
        lat: float,
        lon: float,
        radius_mi: float,
        since_ts: int | None = None,
    ) -> AsyncIterator[Deal]:
        async for data in self._search_pages(retailer, lat, lon, radius_mi, since_ts):
            for group in data.get("grouped_hits", []):
                for hit in group.get("hits", []):
                    yield Deal.from_hit(hit["document"], retailer=retailer)

    async def search_raw(
        self,
        retailer: str,
        lat: float,
        lon: float,
        radius_mi: float,
        since_ts: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for data in self._search_pages(retailer, lat, lon, radius_mi, since_ts):
            for group in data.get("grouped_hits", []):
                for hit in group.get("hits", []):
                    yield hit["document"]
