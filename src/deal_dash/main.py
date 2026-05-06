import asyncio

import click
import zipcodes

from deal_dash.client import RebelsavingsClient
from deal_dash.session import get_session_cookie


RETAILER_CHOICES = ["homedepot", "lowes", "walmart", "walgreens", "tractorsupply"]


def _zip_to_latlon(zip_code: str) -> tuple[float, float]:
    result = zipcodes.matching(zip_code)
    if not result:
        raise click.BadParameter(f"Unknown zip code: {zip_code!r}", param_hint="--zip")
    rec = result[0]
    return float(rec["lat"]), float(rec["long"])


async def _run(retailer: str, zip_code: str, radius: float, min_discount: int) -> None:
    click.echo(f"Fetching {retailer} clearance deals near {zip_code}...")
    lat, lon = _zip_to_latlon(zip_code)
    cookie = await get_session_cookie(retailer)
    client = RebelsavingsClient(session_cookie=cookie)

    deals = []
    async for deal in client.search(retailer, lat, lon, radius):
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
    type=click.Choice(RETAILER_CHOICES),
    help="Retailer to search",
)
@click.option("--radius", default=25.0, show_default=True, help="Search radius in miles")
@click.option("--min-discount", default=0, show_default=True, help="Minimum discount %%")
def cli(zip_code: str, retailer: str, radius: float, min_discount: int) -> None:
    """Fetch clearance deals from rebelsavings.com sorted by discount."""
    asyncio.run(_run(retailer, zip_code, radius, min_discount))
