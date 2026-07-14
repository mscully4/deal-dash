# deal-dash system health check

Reference for an agent (or human) to assess whether the deal-dash pipeline is
actually working, not just deployed. Written 2026-07-13 after a real ~10h
silent outage was caught by manually checking logs — a clean `cdk deploy`
does not imply a healthy system, always check logs/metrics, not just stack
status.

## AWS context

- **Account:** `735029168602`
- **Region:** `us-east-2`
- **Profile:** `default` — always pass `AWS_PROFILE=default --region us-east-2` explicitly. `AWS_REGION` env var does NOT override the profile's configured region.
- Note: this is a shared personal AWS account with unrelated projects (sportsbook/polymarket trading bots, a travel app, etc). Filter everything by `DealDash` / `deal-dash` name prefixes.

## Live architecture (as of 2026-07-13)

```
HiddenClearancesScraper ──┐
                           ├──> deal-dash-deals (DynamoDB) ──stream──> NotifierLambda ──> Discord (message + Like/Dislike buttons)
RebelSavingsScraperV2 ────┘                                                                      │
                                                                                                    ▼
                                                                                     DealInteractionsLambda (API GW)
                                                                                     writes `liked` bool back to deal-dash-deals
```

Three live CDK stacks. There is no embedding/similarity-search component currently — that was retired with the old stack and hasn't been rebuilt.

## CloudFormation stacks

Check all three are `UPDATE_COMPLETE` (or `CREATE_COMPLETE`), not `*_FAILED` or `*_ROLLBACK*`:

```bash
AWS_PROFILE=default aws cloudformation describe-stacks --region us-east-2 \
  --query "Stacks[?starts_with(StackName, 'DealDash')].{Name:StackName,Status:StackStatus}" --output table
```

Expected stacks: `DealDash-DatabaseStack-735029168602-us-east-2`, `DealDash-DealScraperStack-735029168602-us-east-2`, `DealDash-DealConsumerStack-735029168602-us-east-2`.

`DealDash-RebelSavingsStack-*` should **not** exist (retired 2026-07-12). If it's back, something got redeployed that shouldn't have been.

## Lambda functions

Physical names include a random CDK suffix and change on stack replacement — always resolve by prefix, don't hardcode the full name below into automation. Current names (verify freshness, don't trust this table blindly):

| Logical name | Stack | Physical name (as of 2026-07-13) | Trigger |
|---|---|---|---|
| `HiddenClearancesScraper` | DealScraperStack | `DealDash-DealScraperStack-HiddenClearancesScraperF-Nlvo1nAfgPRO` | EventBridge cron, hourly at `:00` |
| `RebelSavingsScraperV2` | DealScraperStack | `DealDash-DealScraperStack-RebelSavingsScraperV2BAE-TJMxUXIu2j2v` | EventBridge cron, hourly at `:30` |
| `NotifierLambda` | DealConsumerStack | `DealDash-DealConsumerStack--NotifierLambdaF56D8BAF-wpwYrMUbMqGE` | DynamoDB Stream on `deal-dash-deals` (INSERT only) |
| `DealInteractionsLambda` | DealConsumerStack | `DealDash-DealConsumerStac-DealInteractionsLambdaA6-pDhRYAfsNNUl` | API Gateway `POST /interactions` (Discord webhook) |

Resolve current names:

```bash
AWS_PROFILE=default aws lambda list-functions --region us-east-2 \
  --query "Functions[?contains(FunctionName,'DealDash')].{Name:FunctionName,State:State,LastModified:LastModified}" --output table
```

`State` should be `Active` for all four. `HiddenClearancesScraper` has `reservedConcurrentExecutions: 1` set deliberately (see "Known failure modes" below) — do not remove it.

### Log groups

`/aws/lambda/<physical function name>` for each of the four above. Stale log groups also exist for the retired `RebelSavingsStack` functions (`EmbedderLambda`, `DiscordHandlerLambda`, `ScraperLambda`) — CloudWatch doesn't delete log groups when the Lambda is destroyed. Ignore those; if they're the only ones with recent events, that itself is a red flag (means the retired stack came back).

### Checking a function actually ran recently

```bash
FN="<physical-function-name>"
AWS_PROFILE=default aws logs describe-log-streams --region us-east-2 \
  --log-group-name "/aws/lambda/$FN" --order-by LastEventTime --descending --max-items 1 \
  --query 'logStreams[0].{Stream:logStreamName,LastEvent:lastEventTimestamp}' --output text
```

Compare `LastEvent` (epoch ms) against expected cadence: HC scraper and RebelSavings scraper should have fired within the last hour; Notifier/DealInteractions only fire on activity (no fixed cadence — silence isn't necessarily bad, but should correlate with scraper activity / no new deals).

### Checking for errors in the last N hours

```bash
AWS_PROFILE=default aws logs filter-log-events --region us-east-2 \
  --log-group-name "/aws/lambda/$FN" \
  --start-time $(( ($(date +%s) - 3600) * 1000 )) \
  --filter-pattern "?ERROR ?Exception ?Traceback" \
  --query 'events[].message' --output text
```

A single transient error is not necessarily an incident. A **repeating identical error across many consecutive log streams** is — DynamoDB Stream Lambdas (`NotifierLambda`) retry failed batches automatically (`bisectBatchOnError: true`), so a code bug there manifests as the same error hundreds of times until fixed and redeployed, not just once.

### Success markers to grep for

| Function | Success log message | Failure signature seen before |
|---|---|---|
| `HiddenClearancesScraper` | `"scraper done"` with `results: {feed, nearby}` counts | `HTTPStatusError ... 400 Bad Request` on Supabase token refresh — see incident below |
| `RebelSavingsScraperV2` | look for `TotalDealsScraped` metric / final log line | — |
| `NotifierLambda` | `"batch received"` then per-record `"notify skipped"` or `"posted to Discord"` | `KeyError: 'retailer'` — fixed 2026-07-13, should not recur |
| `DealInteractionsLambda` | `"interaction received"` then `"liked updated"` | `SignatureFailures` metric spiking = something hitting the endpoint with bad/no signature (expected at low background rate from scanners; a real Discord button click should never fail this) |

## CloudWatch metrics

All custom metrics are in namespace **`deal-dash`**, dimensioned by `service`:

| service | Metric names |
|---|---|
| `hidden-clearances-scraper` | `TotalDealsScraped`, `DealsScraped` (dim `kind`: `feed`/`nearby`), `ScrapeError` (dim `kind`) |
| `rebel-savings-scraper-v2` | `TotalDealsScraped`, `DealsScraped` (dim `retailer`), `ScrapeError` (dim `retailer`) |
| `notifier` | `RecordsProcessed`, `Notified`, `RateLimited`, `SkippedNoConfig`, `SkippedRetailer`, `SkippedLowPrice`, `SkippedDedupe`, `SkippedSparseItem`, `NotifyError` |
| `deal-interactions` | `InteractionsReceived`, `SignatureFailures`, `LikeButtonPressed`, `DislikeButtonPressed` |

**Error metrics (2026-07-14):** each per-item loop (retailer, feed/nearby, DDB record) is wrapped in try/except — one bad item emits `ScrapeError`/`NotifyError` (with the failing retailer/kind/product_key logged) and the loop continues, instead of one exception aborting the whole run/batch. `deal-interactions` is a single-request Lambda behind API Gateway (no batch to protect), so it's left to fail naturally into the native Lambda `Errors` metric rather than swallowing. If any of these named error metrics are nonzero, check the corresponding log group for the `logger.exception` traceback — the metric alone won't have the stack trace.

```bash
AWS_PROFILE=default aws cloudwatch get-metric-statistics --region us-east-2 \
  --namespace deal-dash --metric-name TotalDealsScraped --dimensions Name=service,Value=hidden-clearances-scraper \
  --start-time $(date -u -d '24 hours ago' +%FT%TZ) --end-time $(date -u +%FT%TZ) \
  --period 3600 --statistics Sum
```

**No CloudWatch Alarms are currently configured** for any of this (`aws cloudwatch describe-alarms` returns empty for the `deal-dash` namespace as of 2026-07-13). Health checking is manual/log-based only — worth revisiting if outages keep going unnoticed.

## EventBridge schedules

```bash
AWS_PROFILE=default aws events list-rules --region us-east-2 \
  --query "Rules[?contains(Name,'DealDash')].{Name:Name,Schedule:ScheduleExpression,State:State}" --output table
```

Expected: two `ENABLED` rules, `cron(0 * * * ? *)` (HC scraper) and `cron(30 * * * ? *)` (Rebel Savings scraper). If `State` is `DISABLED`, scraping has been manually paused.

## DynamoDB

**`deal-dash-deals`** (live, PK `product_key`, SK `store_key`, GSI `retailer-category-index` on `retailer`/`category`, stream `NEW_IMAGE` enabled — feeds NotifierLambda):

```bash
AWS_PROFILE=default aws dynamodb describe-table --region us-east-2 --table-name deal-dash-deals \
  --query "Table.{ItemCount:ItemCount,SizeBytes:TableSizeBytes,Status:TableStatus}"
```

`ItemCount`/size are refreshed roughly daily by DynamoDB, not real-time — don't treat a static count over a few hours as a stall signal by itself; cross-check against scraper `TotalDealsScraped` metrics instead.

**`rebel-savings-deals`** (legacy, orphaned as of 2026-07-12 cutover — not CDK-managed, nothing writes to it anymore, kept around only because it hadn't been explicitly deleted yet). If it's still needed for anything, that assumption should be re-verified; otherwise it's a candidate for deletion.

## Secrets Manager

| Secret ID | Purpose | Rotation |
|---|---|---|
| `deal-dash/discord-bot-token-v2` | Discord bot token, used by Notifier + DealInteractions | Static, manual rotation only |
| `deal-dash/hidden-clearances-refresh-token` | Supabase refresh token for HC scraper auth | **Rotates on every scraper invocation** — single-use, see incident below |

```bash
AWS_PROFILE=default aws secretsmanager list-secrets --region us-east-2 \
  --query "SecretList[?contains(Name,'deal-dash')].{Name:Name,LastChanged:LastChangedDate}"
```

`hidden-clearances-refresh-token`'s `LastChangedDate` should track within ~1h of the last successful HC scraper run (it's rewritten every invocation). If it's stale relative to recent scraper log activity, the scraper is failing before reaching the rotation step.

## API Gateway

`deal-dash-interactions` (id `g6sudq8kg8` as of 2026-07-13, resolve via name not id) — `POST /interactions`, backs the Discord Interactions Endpoint URL, routes to `DealInteractionsLambda`.

```bash
AWS_PROFILE=default aws apigateway get-rest-apis --region us-east-2 \
  --query "items[?name=='deal-dash-interactions']"
```

Cross-check against Discord's actual configured endpoint (requires a bot token, see below) — if these drift apart, button clicks silently 404/go nowhere from Discord's perspective, but the Lambda itself will show no errors (it's just not being called).

```bash
TOKEN=$(AWS_PROFILE=default aws secretsmanager get-secret-value --region us-east-2 \
  --secret-id deal-dash/discord-bot-token-v2 --query SecretString --output text)
curl -s -H "Authorization: Bot $TOKEN" https://discord.com/api/v10/oauth2/applications/@me \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['interactions_endpoint_url'])"
```

Should print an `execute-api.us-east-2.amazonaws.com` URL containing the current `deal-dash-interactions` API id.

## Discord

- **App name:** Midas, App ID `1505987881171157073`
- **Channel ID:** see `DISCORD_CHANNEL_ID` in `.envrc` (not committed)
- Notify allowlist (`src/deal_dash/lambdas/notifier/handler.py`): only `homedepot`, `lowes`, `walmart` post to Discord; deals under `$10` are skipped regardless of retailer; same `product_key` is deduped for 2h (`_already_notified` TTL) even across multiple store rows.

## Known failure modes (real incidents, not hypothetical)

1. **HC scraper refresh-token race (2026-07-13, ~10h outage).** Supabase refresh tokens are single-use. Two concurrent invocations of the scraper (a manual test invoke racing the hourly cron, or an EventBridge retry replaying a failed run into the next window) both read the same token; the loser's request is rejected and the token is permanently bricked — not self-healing, no amount of retrying fixes it. Fixed via `reservedConcurrentExecutions: 1` on the scraper + trimmed EventBridge retry policy (`retryAttempts: 0`, `maxEventAge: 5min`). If this recurs, check for overlapping manual invokes before assuming the token itself is corrupt; recovery requires a live browser re-auth (playwriter skill) to reseed `deal-dash/hidden-clearances-refresh-token`, extracting the `sb-cdqqxarqppyvctffzsax-auth-token.0`/`.1` cookie pair from an authenticated hiddenclearances.com session and parsing `refresh_token` out of the reassembled JSON.

2. **NotifierLambda crash-loop on sparse like/dislike upserts (2026-07-13).** `DealInteractionsLambda` upserts `{product_key, store_key, liked}` via `update_item`, which silently creates a new sparse row if that key doesn't already exist (stale button click, or a message posted for a deal that was later deleted). This produces a real DynamoDB Stream `INSERT` event with no `retailer`/`price` fields, which crashed the notifier and got retried indefinitely (`bisectBatchOnError: true`, ~24h stream retention). Fixed: notifier now checks for `retailer`/`price` presence and skips (`SkippedSparseItem` metric) instead of crashing. If `SkippedSparseItem` is elevated, something is generating stale button clicks — not itself an error, but worth knowing about.

3. **Discord 429 rate limiting during backlog drains.** `_post_to_discord` returns `False` (not raise) on HTTP 429 so the notifier doesn't crash-loop the whole DDB stream batch; the record is simply not marked notified and Discord posting is skipped for it (metric: `RateLimited`). Expected during large backlog catch-ups, not during steady-state.
