# Multi-Source Deals Table (Rebel Savings + Hidden Clearances)

**Date:** 2026-07-12
**Status:** Proposed

## Overview

Add Hidden Clearances (`hiddenclearances.com`) as a second deal source alongside Rebel Savings. Both sources cover overlapping retailers (confirmed: Home Depot; likely: Lowe's), so the same physical deal can arrive from either feed. Rather than bolt a second source onto the current single-source schema, recreate `rebel-savings-deals` as a source-agnostic table with a proper cross-source dedupe key.

Existing table data is disposable — acceptable to drop and recreate rather than migrate in place.

---

## Key finding: cross-source identifier

Rebel Savings' `upc` field is a genuine UPC-A barcode. Hidden Clearances' `productId` is Home Depot's internal **Internet #**. These are *different ID spaces* — confirmed by direct comparison (Milwaukee PACKOUT Rack Kit: UPC `045242336036` vs Internet # `330884657`, same physical item/store).

However, Rebel Savings' raw `link` field embeds the same Internet # Hidden Clearances uses:

```
https://www.homedepot.com/p/Milwaukee-PACKOUT-Rack-Kit-48-21-8070/330884657?store=509
                                                                     ^^^^^^^^ matches HC productId
```

**Canonical cross-source key = retailer product ID parsed from the product URL**, not the UPC. UPC stays as a secondary attribute (useful on its own, just not the join key).

**Lowe's — checked, partially confirmed:** Rebel Savings' `upc` field for Lowe's items is likewise Lowe's own item # (e.g. `5017537405`), embedded in the URL the same way. Hidden Clearances' Lowe's `productId` values (`5014593355`, `1000868308`, `1000887`, ...) are the same format/ID scheme — strong signal they're the same ID space, but no single product was found in both sources during this check to confirm numeric equality directly. Reason: Rebel Savings' current Lowe's coverage is entirely big-ticket "lead" deals (dishwashers, wall ovens); Hidden Clearances' `feed` endpoint returns `productId: null` for those same locked/lead deals — **it does not expose the product ID for locked deals at all**, only for unlocked clearance finds (which come through its `nearby` endpoint, a different deal category Rebel Savings doesn't currently scrape for Lowe's). No overlapping title existed in either source's sample to test against.

**Consequence for dedupe design:** the locked-deal ID gap isn't Lowe's-specific — it applies to any Hidden Clearances deal with `locked: true`. Dedupe by `canonical_id` only works when HC exposes one; locked deals fall back to no cross-source merge (they'll sit as separate `sources: {"hiddenclearances"}` items until/unless unlocked).

---

## New table: `deal-dash-deals`

Replaces `rebel-savings-deals`. Renamed to reflect multi-source scope.

| | |
|---|---|
| **PK** | `product_key` = `{retailer}#{canonical_id}` (canonical_id = retailer product ID parsed from URL) |
| **SK** | `store_key` = `store#{store_number}` for in-store, `online` for online-only deals |
| **GSI `retailer-index`** | PK `retailer`, SK `product_key` — needed to list/scan all deals for one retailer (used by embedder context lookups, CLI output, ops queries) |

### Attributes

| Field | Type | Notes |
|---|---|---|
| `product_key` (PK) | S | `{retailer}#{canonical_id}` |
| `store_key` (SK) | S | `store#{n}` \| `online` |
| `retailer` | S | `homedepot`, `lowes`, `walmart`, etc. |
| `canonical_id` | S | retailer product ID (parsed from URL) — the dedupe key |
| `upc` | S, optional | true UPC-A barcode, when known (currently only from Rebel Savings) |
| `title` | S | |
| `price` | N | |
| `original_price` | N, optional | |
| `discount` | N | |
| `category` / `subcategory` | S | |
| `url` | S | canonical product URL |
| `image_url` | S, optional | |
| `stock` | N, optional | |
| `address` / `city` / `state` | S, optional | in-store only |
| `sources` | SS (string set) | `{"rebelsavings"}`, `{"hiddenclearances"}`, or both after merge |
| `source_ids` | M (map) | `{"rebelsavings": "<upc>", "hiddenclearances": "<productId>"}` — preserves per-source raw IDs even if they ever diverge |
| `liked` | BOOL, optional | carried over from current S3 Vectors metadata (see Related Work) |
| `last_updated` | N | epoch, updated on every write from either source |

### Write / merge behavior

`DealStore.put_deal` becomes an upsert:
1. Compute `product_key` + `store_key` from the incoming deal.
2. `UpdateItem` with `ADD sources :s` (string set union) instead of blind `PutItem` overwrite — so a second source writing the same product+store merges into the existing item instead of clobbering `sources`.
3. Fields that differ by source (e.g. slightly different `title` casing, `image_url`) — last-writer-wins is fine; no need for field-level merge logic given both sources describe the same real-world listing.

---

## Hidden Clearances client

New `src/deal_dash/hidden_clearances/` package, mirroring `rebel_savings/`:

- **Auth:** Supabase refresh-token flow (see prior recon). One-time bootstrap extracts `refresh_token` from browser cookie via Playwright, seeds AWS Secrets Manager. Every run:
  1. `POST https://cdqqxarqppyvctffzsax.supabase.co/auth/v1/token?grant_type=refresh_token` with `apikey: <public anon key>` + stored `refresh_token`
  2. Receive fresh `access_token` **and rotated `refresh_token`**
  3. Write the new `refresh_token` back to Secrets Manager immediately (rotation is one-shot — reusing a stale token invalidates the session)
  4. Use `access_token` as `Authorization: Bearer` on `GET https://api.hiddenclearances.com/api/v1/feed?page=N&limit=8&sort=recommended&kind=curated` (paginate until empty page)
- **Parsing:** map feed response → same internal `Deal`-shaped record (`retailer`, `canonical_id` = `productId`, `title`, `price`, `originalPrice`, `discountPercent`, `kind` → in-store/online, etc.)
- No Playwright needed at runtime — pure HTTP after the one-time cookie bootstrap.

---

## Touch list

| File | Change |
|---|---|
| `src/deal_dash/rebel_savings/models.py` | `Deal.item_id` → replaced by `product_key`/`store_key` computed fields; add `canonical_id` parsed from `url` |
| `src/deal_dash/rebel_savings/dynamo.py` | `DealStore.put_deal` → upsert with `sources` merge; rename table env var default to `deal-dash-deals` |
| `src/deal_dash/hidden_clearances/client.py` (new) | Supabase auth + feed pagination |
| `src/deal_dash/hidden_clearances/models.py` (new) | HC response → shared deal shape |
| `src/deal_dash/hidden_clearances/auth.py` (new) | refresh-token rotation against Secrets Manager |
| `src/deal_dash/lambdas/scrapers/rebel_savings.py` | either extend to also invoke HC client, or add sibling `hidden_clearances.py` scraper Lambda on its own schedule |
| `src/deal_dash/lambdas/embedder/handler.py` | stream consumer reads new key shape (`product_key`/`store_key` instead of `retailer`/`item_id`); vector key uses `canonical_id` instead of raw `upc` |
| `lib/stacks/rebel-savings-stack.ts` | table replacement (new key schema forces physical replacement anyway), new GSI, Secrets Manager secret for HC refresh token, IAM for HC Lambda if added |
| `CLAUDE.md` | update table name, PK/SK docs, add Hidden Clearances section |

---

## Migration

1. **Done:** CDK now defines `deal-dash-deals` as a new table (new logical ID `DealDashDealsTable`, new PK/SK). `rebel-savings-deals` keeps its `RemovalPolicy.RETAIN` and is orphaned from the stack on next deploy — not deleted. The existing scraper/embedder keep running against it unmodified until step 2 ships.
2. Update `DealStore` / `Deal` model / embedder handler together (interdependent — must ship as one deploy) to read/write `deal-dash-deals`.
3. Backfill not required — table repopulates naturally on next scrape cycle for both sources.
4. Once cutover is confirmed working (scraper + embedder both healthy against the new table), manually delete `rebel-savings-deals` — it's no longer CDK-managed at that point, so this is a manual `aws dynamodb delete-table`, not a CDK change.

---

## Related work (out of scope here, but adjacent)

- **S3 Vectors → in-DDB brute-force cosine**: separately discussed cost concern (S3 Vectors billing). If pursued, `liked` and `embedding` attributes would live directly on the `deal-dash-deals` item, keyed by `canonical_id` rather than raw UPC — same canonical ID this proposal introduces, so the two changes compose cleanly if done together or in sequence.

---

## Open questions

- Does Hidden Clearances cover any retailers Rebel Savings doesn't (or vice versa) where dedupe is moot and this is purely additive?
- Polling cadence for Hidden Clearances — same hourly cadence as the Rebel Savings scraper Lambda, or different given it's a different rate-limit/auth surface?
- ~~Lowe's canonical ID verification~~ — checked; format matches but not proven equal (see above). Revisit once both sources have overlapping Lowe's coverage, or treat `locked: true` HC deals as permanently non-dedupeable via ID.
