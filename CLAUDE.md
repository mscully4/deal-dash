# deal-dash

Fetches clearance deals from rebelsavings.com, stores them in DynamoDB, and generates vector embeddings via a Lambda pipeline for semantic search.

## Architecture

```
CLI (deal-dash) → RebelsavingsClient → DynamoDB (rebel-savings-deals)
                                              ↓ DDB Stream
                                       EmbedderLambda
                                       → Bedrock (Titan Embed v2)
                                       → S3 Vectors (deal-dash-vectors/deals)
```

## AWS

- **Region:** `us-east-2`
- **Profile:** `default`
- **DynamoDB table:** `rebel-savings-deals` (PK: `retailer`, SK: `item_id`)
- **S3 Vectors bucket:** `deal-dash-vectors`, index: `deals`, 256-dim cosine float32
- **Embedder Lambda:** triggered by DDB stream, embeds title+category, keys vector by UPC

Always use `AWS_PROFILE=default --region us-east-2` for AWS CLI commands. The `AWS_REGION` env var does NOT override the profile's configured region (`us-west-2`) — use the `--region` flag instead.

### Lambda functions (us-east-2)

| Function | Log group |
|----------|-----------|
| `DealDash-RebelSavingsStac-DiscordHandlerLambda1C0A-Z9FYpKaIjPdC` | `/aws/lambda/DealDash-RebelSavingsStac-DiscordHandlerLambda1C0A-Z9FYpKaIjPdC` |
| `DealDash-RebelSavingsStack-7-ScraperLambda4C38B115-76E47U8eCqyf` | `/aws/lambda/DealDash-RebelSavingsStack-7-ScraperLambda4C38B115-76E47U8eCqyf` |
| `DealDash-RebelSavingsStack--EmbedderLambdaA8002AC3-3hB9OqIfpH6M` | `/aws/lambda/DealDash-RebelSavingsStack--EmbedderLambdaA8002AC3-3hB9OqIfpH6M` |

```bash
# Tail Lambda logs
AWS_PROFILE=default aws logs get-log-events --region us-east-2 \
  --log-group-name "/aws/lambda/<function>" \
  --log-stream-name "$(AWS_PROFILE=default aws logs describe-log-streams --region us-east-2 \
    --log-group-name '/aws/lambda/<function>' --order-by LastEventTime --descending \
    --max-items 1 --query 'logStreams[0].logStreamName' --output text)"
```

## Commands

```bash
# Run CLI
uv run deal-dash --zip 78681 --days 1

# Tests
uv run pytest

# Lint / type check
uv run ruff check && uv run mypy src

# Deploy infra
npx cdk deploy --profile default
```

## Key files

| Path | Purpose |
|------|---------|
| `src/deal_dash/rebel_savings/cli.py` | CLI entry point (click) |
| `src/deal_dash/rebel_savings/client.py` | HTTP client for rebelsavings.com API |
| `src/deal_dash/rebel_savings/models.py` | `Deal` pydantic model |
| `src/deal_dash/rebel_savings/dynamo.py` | DynamoDB write (`DealStore`) |
| `src/deal_dash/rebel_savings/session.py` | Playwright session cookie handshake |
| `src/deal_dash/lambdas/scrapers/rebel_savings.py` | Scraper Lambda handler (hourly, all retailers) |
| `src/deal_dash/lambdas/embedder/handler.py` | DDB stream → Bedrock → S3 Vectors |
| `lib/stacks/rebel-savings-stack.ts` | CDK stack (DDB, Lambda, S3 Vectors) |

## Rebel Savings API notes

- **Anti-scraping:** requires full browser headers (`sec-ch-ua*`, `sec-fetch-*`) or returns synthetic/fake data
- **Retailer codes:** CLI name maps to API code — `homedepot→hd`, `lowes→lowes`, `walmart→walmart`, `walgreens→walgreens`, `tractorsupply→tsc`
- **Response shape:** `groupBy: "title"` → response uses `grouped_hits[]` not `hits[]`
- **Session cookie:** `rs_session` fetched lazily via Playwright on first request; cached on client instance

## Vector design

- Keyed by **UPC** (product-level, not store-level)
- Metadata: `retailer`, `category`, `discount`, `price`, `liked` (bool; omitted when null — S3 Vectors rejects null)
- Text input to embedder: `"{title} {category} {subcategory}"`
