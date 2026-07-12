"""Force-post specific UPCs to Discord. One-off backfill script."""
from typing import Any

import boto3
import httpx
from boto3.dynamodb.conditions import Key


REGION = "us-east-2"
TABLE = "rebel-savings-deals"
VECTOR_BUCKET = "deal-dash-vectors"
VECTOR_INDEX = "deals"
DISCORD_BOT_TOKEN_ARN = "arn:aws:secretsmanager:us-east-2:735029168602:secret:deal-dash/discord-bot-token-TKTApb"
DISCORD_CHANNEL_ID = "1505984839017431201"

UPCS = [
    "5001955651",
    "5013037845",
    "5015405095",
    "5017058219",
]

session = boto3.Session(region_name=REGION)
ddb = session.resource("dynamodb")
table = ddb.Table(TABLE)
sm = session.client("secretsmanager")
s3v = session.client("s3vectors")

_RETAILER_DISPLAY: dict[str, str] = {
    "homedepot": "Home Depot",
    "lowes": "Lowe's",
    "walmart": "Walmart",
    "walgreens": "Walgreens",
    "tractorsupply": "Tractor Supply",
}


def get_bot_token() -> str:
    return sm.get_secret_value(SecretId=DISCORD_BOT_TOKEN_ARN)["SecretString"]


def get_liked(upc: str) -> bool | None:
    resp = s3v.get_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=VECTOR_INDEX,
        keys=[upc],
        returnData=False,
        returnMetadata=True,
    )
    vecs = resp.get("vectors", [])
    if vecs:
        val = vecs[0].get("metadata", {}).get("liked")
        if isinstance(val, bool):
            return val
    return None


def post_to_discord(doc: dict[str, Any], token: str, liked: bool | None) -> None:
    retailer_display = _RETAILER_DISPLAY.get(doc["retailer"], doc["retailer"])
    fields: list[dict[str, Any]] = [
        {"name": "Retailer", "value": retailer_display, "inline": True},
        {"name": "Price", "value": f"${float(doc['price']):.2f}", "inline": True},
        {"name": "Discount", "value": f"{doc['discount']}% off", "inline": True},
        {"name": "Category", "value": doc["category"], "inline": True},
        {
            "name": "Location",
            "value": f"{doc['address']}, {doc['city']}, {doc['state']}",
            "inline": True,
        },
    ]
    if liked is True:
        fields.append({"name": "Status", "value": "👍 Previously liked", "inline": True})
    elif liked is False:
        fields.append({"name": "Status", "value": "👎 Previously disliked", "inline": True})

    upc = doc["upc"]
    embed: dict[str, Any] = {
        "title": doc["title"],
        "url": doc["url"],
        "color": 0x2ECC71,
        "fields": fields,
    }
    if image_url := doc.get("image_url"):
        embed["image"] = {"url": image_url}

    message = {
        "embeds": [embed],
        "components": [
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 3, "label": "👍 Like", "custom_id": f"like:{upc}"},
                    {"type": 2, "style": 4, "label": "👎 Dislike", "custom_id": f"dislike:{upc}"},
                ],
            }
        ],
    }
    resp = httpx.post(
        f"https://discord.com/api/v10/channels/{DISCORD_CHANNEL_ID}/messages",
        headers={"Authorization": f"Bot {token}"},
        json=message,
        timeout=10.0,
    )
    resp.raise_for_status()


def main() -> None:
    token = get_bot_token()
    posted = 0
    for upc in UPCS:
        resp = table.query(
            KeyConditionExpression=Key("retailer").eq("lowes") & Key("item_id").begins_with(upc),
        )
        items = resp.get("Items", [])
        if not items:
            print(f"NOT FOUND in DDB: {upc}")
            continue
        # post best-discount item if multiple stores
        doc = max(items, key=lambda x: int(x.get("discount", 0)))
        liked = get_liked(upc)
        post_to_discord(doc, token, liked)
        print(f"posted: {doc['title']} ({upc}) liked={liked}")
        posted += 1

    print(f"\n{posted}/{len(UPCS)} posted")


if __name__ == "__main__":
    main()
