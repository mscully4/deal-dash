import asyncio
import json
from datetime import datetime, timedelta, timezone

import click
import zipcodes

from deal_dash.rebel_savings.client import RebelsavingsClient
from deal_dash.rebel_savings.constants import Retailer
from deal_dash.rebel_savings.dynamo import DealStore


def _zip_to_latlon(zip_code: str) -> tuple[float, float]:
    result = zipcodes.matching(zip_code)
    if not result:
        raise click.BadParameter(f"Unknown zip code: {zip_code!r}", param_hint="--zip")
    rec = result[0]
    return float(rec["lat"]), float(rec["long"])


async def _run(
    retailer: str,
    zip_code: str,
    radius: float,
    min_discount: int,
    days: int | None,
    debug_raw: bool,
    debug_count: int,
) -> None:
    lat, lon = _zip_to_latlon(zip_code)
    since_ts: int | None = None
    if days is not None:
        since_ts = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    client = RebelsavingsClient()

    if debug_raw:
        seen = 0
        async for raw in client.search_raw(retailer, lat, lon, radius, since_ts):
            click.echo(json.dumps(raw, indent=2, default=str))
            seen += 1
            if seen >= debug_count:
                return
        return

    click.echo(f"Fetching {retailer} clearance deals near {zip_code}...")
    store = DealStore()

    deals = []
    async for deal in client.search(retailer, lat, lon, radius, since_ts):
        store.put_deal(deal)
        if deal.discount >= min_discount:
            deals.append(deal)

    deals.sort(key=lambda d: d.discount, reverse=True)

    if not deals:
        click.echo("No deals found matching your criteria.")
        return

    click.echo(f"\nFound {len(deals)} deals:\n")
    for deal in deals:
        click.echo(f"{deal.discount:>3}%  ${deal.price:<8.2f} {deal.title}")
        click.echo(f"             {deal.url}")
        click.echo()


@click.command()
@click.option("--zip", "zip_code", required=True, help="Zip code to search near")
@click.option(
    "--retailer",
    default="homedepot",
    show_default=True,
    type=click.Choice([r.value for r in Retailer]),
    help="Retailer to search",
)
@click.option("--radius", default=25.0, show_default=True, help="Search radius in miles")
@click.option("--min-discount", default=0, show_default=True, help="Minimum discount %%")
@click.option("--days", default=None, type=int, help="Only show deals added in the last N days")
@click.option(
    "--debug-raw", is_flag=True, default=False, help="Print raw API hits as JSON and exit"
)  # noqa: E501
@click.option(
    "--debug-count",
    default=10,
    show_default=True,
    help="Number of raw hits to print with --debug-raw",
)  # noqa: E501
def cli(
    zip_code: str,
    retailer: str,
    radius: float,
    min_discount: int,
    days: int | None,
    debug_raw: bool,
    debug_count: int,
) -> None:
    """Fetch clearance deals from rebelsavings.com sorted by discount."""
    asyncio.run(_run(retailer, zip_code, radius, min_discount, days, debug_raw, debug_count))
