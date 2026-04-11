# WFH Coffee Shop Finder — V2 Architecture Plan

## Context

V1 enriched places on every map pan — triggering Tavily + LLM jobs inline with user requests. This caused high latency, redundant enrichment of the same places, and no persistent web-scraped data. V2 flips the model: the map is a **read-only view** into a pre-built, fully enriched database. All expensive work happens offline in a background crawler pipeline. The normalized schema (4 tables) replaces V1's flat JSONB blob.

---

## Directory Structure Note

The `backend/` folder IS the FastAPI backend — deployed to Render exactly as in V1. What changes is the internal organization:

- V1 had an extra nesting layer (`backend/api/main.py`) plus a separate `backend/enrichment/` folder that coupled all enrichment concerns together
- V2 flattens to `backend/main.py` (the FastAPI entry point, run by Uvicorn as `uvicorn main:app`) and splits the old `enrichment/` responsibilities into `routers/`, `services/`, `background/`, and `crawler/` — each with a clear single responsibility

`config.py` centralizes all `os.environ` reads (scattered across V1 files) into one `pydantic-settings` class so missing env vars crash at startup, not mid-request.

---

## File Structure Overview

```
coffee_app/
├── supabase/
│   ├── migrations/
│   │   ├── 001_create_tables.sql
│   │   ├── 002_create_indexes.sql
│   │   └── 003_create_triggers.sql
│   └── seed/
│       └── nyc_regions.sql
├── backend/
│   ├── main.py
│   ├── config.py
│   ├── models/
│   │   ├── place.py
│   │   ├── mention.py
│   │   └── region.py
│   ├── routers/
│   │   ├── places.py
│   │   ├── mentions.py
│   │   └── regions.py
│   ├── services/
│   │   ├── supabase_client.py
│   │   ├── google_places.py
│   │   ├── region_detector.py
│   │   └── place_filter.py
│   ├── background/
│   │   ├── seed_job.py
│   │   └── scheduler.py
│   └── crawler/
│       ├── orchestrator.py
│       ├── sources/
│       │   ├── tavily_crawler.py
│       │   ├── brave_crawler.py
│       │   ├── yelp_crawler.py
│       │   └── instagram_crawler.py
│       ├── place_resolver.py
│       ├── llm_extractor.py
│       └── db_writer.py
├── coffee-map/                     # existing Next.js app
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── globals.css
│   │   └── api/
│   │       ├── places/
│   │       │   ├── route.ts
│   │       │   └── [place_id]/mentions/route.ts
│   │       └── regions/route.ts
│   ├── components/
│   │   ├── map/
│   │   │   ├── MapContainer.tsx
│   │   │   ├── PlacePin.tsx
│   │   │   ├── InfoCard.tsx
│   │   │   ├── AttributePills.tsx
│   │   │   └── ColdRegionBanner.tsx
│   │   └── ui/
│   │       ├── ScoreBadge.tsx
│   │       ├── PlatformPill.tsx
│   │       └── MentionCard.tsx
│   ├── hooks/
│   │   ├── useMapBounds.ts
│   │   ├── usePlaces.ts
│   │   └── useMentions.ts
│   ├── lib/
│   │   ├── api-client.ts
│   │   └── map-utils.ts
│   ├── types/
│   │   └── index.ts
│   └── next.config.ts
└── .env.example
```

---

## Layer 1: Supabase

### `supabase/migrations/001_create_tables.sql`
**Purpose:** Defines all four normalized tables with constraints and foreign keys.

Key DDL highlights:
- Custom enum types: `region_status ('cold'|'crawling'|'seeded')`, `noise_level`, `platform_type`, `extraction_method`
- `mentions.url` has `UNIQUE` constraint (primary dedup key)
- `UNIQUE (place_id, url)` belt-and-suspenders index on mentions
- `wfh_score`, `mention_count`, `source_count` on `places` are trigger-owned — no app writes them directly
- `sources` needs a `UNIQUE (platform, handle_or_domain)` constraint to prevent duplicate source rows from concurrent crawlers

Key gotcha: `region_id` on `places` is assigned at crawl time. A place straddling two region bounding boxes gets assigned to the region whose centroid is closest.

---

### `supabase/migrations/002_create_indexes.sql`
**Purpose:** All performance indexes for the map pan hot path and crawler write path.

Critical indexes:
```sql
-- Hot path: bounding box filter
CREATE INDEX idx_places_lat_lng ON places(lat, lng);

-- Hot path: partial index for pin-eligible places only
CREATE INDEX idx_places_score_filtered ON places(place_id, wfh_score)
  WHERE wfh_score >= 6.0;

-- Click flow: mentions ordered by confidence
CREATE INDEX idx_mentions_place_laptop ON mentions(place_id, laptop_confidence DESC);

-- Crawler dedup
CREATE UNIQUE INDEX idx_mentions_url ON mentions(url);

-- Region bounding box lookup
CREATE INDEX idx_regions_bbox ON regions(min_lat, max_lat, min_lng, max_lng);

-- Source dedup
CREATE UNIQUE INDEX idx_sources_platform_handle ON sources(platform, handle_or_domain);
```

Key gotcha: The partial index `WHERE wfh_score >= 6.0` means Postgres never scans sub-threshold rows on the pin-return query — biggest single latency win.

---

### `supabase/migrations/003_create_triggers.sql`
**Purpose:** `AFTER INSERT ON mentions` trigger that recomputes `wfh_score`, `mention_count`, `source_count` on the parent `places` row.

Score formula (0–10 scale, coefficients sum to 10.0):
```
wfh_score = (avg_wifi_confidence × 2.5)
           + (avg_outlet_confidence × 2.0)
           + (avg_noise_confidence × 2.0)
           + (avg_laptop_confidence × 3.5)
           + curated_boost (capped at +2.0)
```

Key gotchas:
- `source_count` uses `COUNT(DISTINCT source_id)` — 10 Reddit posts from one subreddit = 1 source
- `has_wifi`, `has_outlets`, `noise_level`, `is_laptop_friendly` are NOT set by this trigger — they are majority-vote aggregations set by `db_writer.recompute_boolean_attrs_for_region` after a full crawl
- Trigger fires `FOR EACH ROW`; acceptable for Phase 1. If batch-insert performance degrades, switch to `FOR EACH STATEMENT` with a staging approach
- `ROUND(v_wfh_score::numeric, 1)` stores scores as 1-decimal floats matching UI badge format ("8.4")

---

### `supabase/seed/nyc_regions.sql`
**Purpose:** Pre-seeds NYC borough bounding boxes with `status='cold'`.

**Manhattan-only guardrail:** For Phase 1, only Manhattan is seeded. The other four boroughs are commented out and will be uncommented in Phase 2. This prevents the cold-region seed job from being triggered for Brooklyn/Queens/Bronx/Staten Island during the MVP period — any pan to those boroughs returns `region_status=null` (no region row exists), and the frontend renders no pins and no banner.

```sql
-- Phase 1: Manhattan only
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('nyc-manhattan', 'cold', 40.6998, 40.8820, -74.0479, -73.9067);

-- Phase 2 (uncomment when ready to expand):
-- ('nyc-brooklyn',      'cold', 40.5700, 40.7395, -74.0419, -73.8334),
-- ('nyc-queens',        'cold', 40.5430, 40.8007, -73.9621, -73.7004),
-- ('nyc-bronx',         'cold', 40.7855, 40.9176, -73.9338, -73.7654),
-- ('nyc-staten-island', 'cold', 40.4960, 40.6490, -74.2591, -74.0522)
```

Key gotcha: Insert as `cold`, NOT `seeded`. The crawler flips status. Inserting as `seeded` without data would hide the empty state from operators.

---

## Layer 2: Shared Types

### `coffee-map/types/index.ts`
**Purpose:** Single source of truth for all TypeScript interfaces used across frontend.

Key types:
```typescript
export type NoiseLevel = 'quiet' | 'moderate' | 'loud'
export type Platform = 'reddit' | 'instagram' | 'blog' | 'tiktok' | 'google_review'

export interface MapBounds { north: number; south: number; east: number; west: number }

export interface PlacePin {
  place_id: string; name: string; address: string; lat: number; lng: number
  wfh_score: number
  has_wifi: boolean | null; has_outlets: boolean | null
  is_laptop_friendly: boolean | null; noise_level: NoiseLevel | null
  seating_comfort: string | null; mention_count: number; source_count: number
}

export interface MentionCard {
  id: string; url: string; evidence_snippet: string | null
  platform: Platform; handle_or_domain: string
  laptop_confidence: number; mentioned_at: string | null
}

export interface NearbySearchResponse {
  places: PlacePin[]
  region_status: 'seeded' | 'crawling' | 'cold' | null
  region_id: string | null
}

export interface NearbySearchRequest { lat: number; lng: number; bounds: MapBounds }
export interface MentionsResponse { place_id: string; mentions: MentionCard[] }
```

Key gotcha: All boolean attrs on `PlacePin` are `| null` — newly crawled places may not have boolean attrs computed yet. UI must guard against null before rendering pills.

---

## Layer 3: FastAPI Backend

### `backend/config.py`
**Purpose:** Centralized env var reads via `pydantic-settings`; fails loudly at startup if any required key is missing.

Key class: `Settings(BaseSettings)` with fields for all API keys (`OPENAI_API_KEY`, `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`, `YELP_API_KEY`, `GOOGLE_PLACES_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`), and tunable thresholds (`pin_score_threshold=6.0`, `pin_laptop_confidence_threshold=0.7`). Inject via `Depends(get_settings)` in routers — never import at module level (breaks unit test injection). No Reddit keys.

---

### `backend/models/place.py`
**Purpose:** Pydantic models for place-related request/response payloads.

Key models:
- `MapBounds` — uses Google Maps naming (`north/south/east/west`), translated to Supabase column names in `region_detector.py`
- `NearbySearchRequest(lat, lng, bounds: MapBounds)`
- `PlacePinResponse` — mirrors `PlacePin` TypeScript interface
- `NearbySearchResponse(places, region_status, region_id)`

### `backend/models/mention.py`
Key models: `MentionCardResponse`, `MentionsResponse`

### `backend/models/region.py`
Key models: `RegionRow` with all region table fields

---

### `backend/services/supabase_client.py`
**Purpose:** Singleton `supabase-py` wrapper with typed async query helpers.

Key functions:
```python
def get_supabase() -> Client  # module-level singleton

async def get_places_by_ids(
    place_ids: list[str],
    score_threshold: float,
    laptop_confidence_threshold: float
) -> list[dict]
# SELECT places WHERE place_id = ANY(place_ids)
#   AND wfh_score >= threshold
#   AND place_id IN (SELECT place_id FROM mentions WHERE laptop_confidence > threshold)

async def get_mentions_for_place(place_id: str) -> list[dict]
# SELECT mentions.*, sources.platform, sources.handle_or_domain
# FROM mentions JOIN sources ON source_id ORDER BY laptop_confidence DESC

async def get_overlapping_regions(bounds: MapBounds) -> list[dict]
async def set_region_status(region_id: str, status: str) -> None
async def upsert_place(place_data: dict) -> None
async def insert_mention_if_new(mention_data: dict) -> bool
```

Key gotchas:
- `laptop_confidence` filter requires a subquery into `mentions` — cannot be a column filter on `places`
- `supabase-py` v2 is synchronous; wrap calls in `asyncio.to_thread` to avoid blocking the event loop
- Service role key bypasses RLS — never log or expose

---

### `backend/services/google_places.py`
**Purpose:** Wraps Google Places API for two specific uses only: Nearby Search (map pan hot path) and Text Search (place resolver). Never requests rich/enterprise fields — only basic fields to avoid Enterprise SKU billing.

Key functions:
```python
async def nearby_search_parallel(lat, lng, radius_meters) -> list[str]
# Fires 3 concurrent requests (cafe, bakery, library), deduplicates place_ids
# Requests basic fields only: place_id, displayName, location, types

async def text_search(query: str, location_bias: dict) -> list[dict]
# Used by place_resolver only; returns {place_id, name, lat, lng, formatted_address}
# Basic fields only — never requests reviews, photos, or editorial summaries
```

Key gotchas:
- **Never request reviews, photos, opening_hours, or editorial summaries** — these trigger Enterprise SKU (~$0.040/req vs ~$0.006/req basic)
- `coffee_shop` is NOT a valid Google Places `nearbysearch` type — use `cafe` only
- Do not combine `rankby=distance` and `radius` — mutually exclusive in the API
- 3 types × 20 results = up to ~60 raw candidates before dedup
- Google Places reviews are NOT used as a crawler content source — Tavily, Brave, and Yelp cover that

---

### `backend/services/region_detector.py`
**Purpose:** Determines whether a viewport is `seeded`, `crawling`, or `cold` by checking against the `regions` table.

Key function:
```python
async def detect_region_for_viewport(bounds: MapBounds) -> tuple[str | None, str]
# Returns (region_id | None, status)
# Priority: seeded > crawling > cold
# When multiple regions are cold, pick the one with greatest overlap for the seed job
```

---

### `backend/services/place_filter.py`
**Purpose:** Pure filter — takes raw Google `place_id` list, returns only DB-matched eligible places.

```python
async def filter_eligible_places(
    candidate_place_ids: list[str],
    score_threshold: float,
    laptop_confidence_threshold: float
) -> list[PlacePinResponse]
```

Key gotcha: If `candidate_place_ids` is empty, return `[]` immediately — no DB hit needed.

---

### `backend/routers/places.py`
**Purpose:** `POST /places/nearby-search` — the hot-path endpoint for all map pan events.

```python
@router.post("/nearby-search", response_model=NearbySearchResponse)
async def nearby_search(req: NearbySearchRequest, background_tasks: BackgroundTasks, settings=Depends(get_settings))
```

Sequence:
1. `asyncio.gather` to run Google Nearby Search + region detection **in parallel** (biggest latency win)
2. `place_filter.filter_eligible_places` with thresholds from settings
3. If cold region: `background_tasks.add_task(trigger_seed, region_id, ...)` (non-blocking)
4. Return `NearbySearchResponse` immediately

Key gotchas:
- Steps 1a and 1b MUST be `asyncio.gather`'d — do not await sequentially
- Background task must re-check `status='cold'` with a conditional UPDATE (TOCTOU race)

---

### `backend/routers/mentions.py`
**Purpose:** `GET /places/{place_id}/mentions` — click-to-expand flow.

```python
@router.get("/{place_id}/mentions", response_model=MentionsResponse)
async def get_mentions(place_id: str, settings=Depends(get_settings))
# Supabase: SELECT mentions JOIN sources WHERE place_id ORDER BY laptop_confidence DESC
```

Key gotcha: No pagination in Phase 1; add `LIMIT 20` as a safety valve with optional `limit` query param.

---

### `backend/routers/regions.py`
**Purpose:** Admin-only routes for region inspection and manual seed triggering. Not called by the frontend.

```python
@router.get("/")  # list all regions
@router.post("/{region_id}/seed")  # manually trigger seed job
```

Protect with `X-Admin-Key` header check against env var.

---

### `backend/main.py`
**Purpose:** FastAPI app factory — registers routers, configures CORS, mounts middleware.

Key gotchas:
- CORS `allow_origins` must be the exact Vercel frontend URL — never `["*"]` in production
- Health endpoint `GET /health` required for Render's health check (otherwise pod restarts loop)
- Start APScheduler (if used) via `lifespan` context manager, not module-level `scheduler.start()`

---

## Layer 4: Background Crawler Pipeline

### `backend/background/seed_job.py`
**Purpose:** Entry point for seeding a cold region. Called via FastAPI `BackgroundTasks`.

```python
async def trigger_seed(region_id: str, center_lat: float, center_lng: float, city_slug: str) -> None
```

Sequence:
1. `UPDATE regions SET status='crawling' WHERE id=? AND status='cold'` → if 0 rows affected, abort (already claimed — idempotency lock)
2. `await orchestrator.run_for_region(...)`
3. `UPDATE regions SET status='seeded', last_crawled_at=now()`
4. On exception: rollback to `status='cold'` so next pan can retry

---

### `backend/background/scheduler.py`
**Purpose:** APScheduler cron for weekly re-crawl of stale seeded regions. Phase 1 optional — MVP can skip this and use manual `/regions/{id}/seed` calls.

---

### `backend/crawler/orchestrator.py`
**Purpose:** Coordinates all crawler sources in priority order; the backbone of the offline pipeline.

```python
async def run_for_region(region_id: str, center_lat: float, center_lng: float, city_slug: str) -> None
```

Sequence:
1. Tavily → Brave → Yelp → Instagram (sequential, not parallel, to respect Google Places Text Search rate limits since all sources feed the same place resolver)
2. For each `RawMention`: resolve → extract → write
3. After all mentions written: `db_writer.recompute_boolean_attrs_for_region(region_id)`

**Manhattan-only guardrail:** The orchestrator checks `city_slug` at the start and raises `ValueError` for any slug other than `nyc-manhattan` until Phase 2. This is a hard stop — not just a seed file omission — so that even a manual API call to `/regions/{id}/seed` for a non-Manhattan region fails loudly rather than silently burning API quota.

```python
ALLOWED_CITY_SLUGS = {"nyc-manhattan"}  # expand in Phase 2

async def run_for_region(...):
    if city_slug not in ALLOWED_CITY_SLUGS:
        raise ValueError(f"Crawling not enabled for {city_slug} — Phase 2 only")
    ...
```

Key gotcha: DB trigger handles `wfh_score`/`mention_count`/`source_count` per-mention. Boolean attr aggregation (`has_wifi`, `has_outlets`, etc.) is a separate batch UPDATE after all mentions are written.

---

### `backend/crawler/sources/tavily_crawler.py`
**Purpose:** Primary web crawler. Runs 15–20 targeted queries per region to maximize URL coverage from blogs, Medium, Reddit threads, Yelp pages, and local guides.

```python
async def fetch_tavily_mentions(city_slug: str, queries: list[str] | None = None) -> list[RawMention]
```

Uses `search_depth='basic'` (not `'advanced'`) — Tavily basic returns URLs + short snippets cheaply. Pages are then scraped directly with `httpx` for full content, avoiding Tavily's per-result content cost.

Query strategy (multi-level, built from `city_slug`):
```python
# City-level
"best coffee shops work from laptop NYC 2024"
"WFH friendly cafe New York wifi outlets"

# Borough/neighborhood-level (Manhattan-specific for Phase 1)
"best cafes to work from Manhattan wifi"
"work from coffee shop Midtown outlets quiet"
"cafe wifi outlets Lower East Side Manhattan"
"coffee shop work SoHo Manhattan"
"WFH cafe Upper West Side laptop friendly"

# Attribute-focused
"NYC coffee shop strong wifi no time limit"
"quiet cafe Manhattan good for working"
"NYC cafe lots of outlets work from home"

# Site-targeted (surfaces Reddit + Yelp without direct API access)
"site:reddit.com coffee shop work laptop nyc manhattan"
"site:yelp.com best coffee shops work nyc manhattan"
"site:nymag.com best cafes work from home NYC"
"site:timeout.com best NYC cafes to work from"
```

Deduplicates by URL across all queries. 0.5s delay between queries. ~15 queries × $0.01 = ~$0.15 per region crawl.

---

### `backend/crawler/sources/brave_crawler.py`
**Purpose:** Cheaper bulk URL discovery complement to Tavily, used for high-volume neighborhood-level queries where breadth matters more than content depth.

```python
async def fetch_brave_mentions(city_slug: str, queries: list[str] | None = None) -> list[RawMention]
# POST https://api.search.brave.com/res/v1/web/search
# Returns URLs + snippets at ~$3/1000 queries vs Tavily's higher rates
```

Uses the same multi-query pattern as Tavily but targets neighborhood-level queries where Tavily coverage may thin out. URLs discovered here are scraped with `httpx` for content. Deduplicates against URLs already collected by Tavily (pass seen_urls set into both crawlers).

Key gotcha: Brave Search API requires `Accept: application/json` and `X-Subscription-Token` headers. Rate limit varies by plan — add 0.3s delay between requests.

---

### `backend/crawler/sources/yelp_crawler.py`
**Purpose:** Free structured source. Searches Yelp Fusion API for cafes in the region, returns business data + review snippets. No place resolution needed — Yelp returns lat/lng directly, confirmed against Google `place_id` via Text Search.

```python
async def fetch_yelp_mentions(city_slug: str) -> list[RawMention]
# GET https://api.yelp.com/v3/businesses/search
#   ?term=coffee&location=Manhattan,NYC&categories=cafes&limit=50
# Paginates with offset up to 200 results
# Each business: name, address, lat/lng, rating, up to 3 review snippets
```

Each Yelp business becomes a `RawMention` per review snippet. The business `name + address` is passed to `place_resolver` to confirm Google `place_id` (one Text Search call per unique business, cached within the crawl run). Free tier: 500 calls/day.

Key gotcha: Yelp review snippets are short (snippet only, not full review text). They're still valuable as structured signal — a snippet saying "great wifi, lots of outlets" is enough for high-confidence extraction.

---

### `backend/crawler/sources/instagram_crawler.py`
**Purpose:** Fetches captions from a hardcoded curated list of public WFH-recommendation accounts.

```python
CURATED_ACCOUNTS = ["workfromcafe", "nycofficelounge", "wfhnyc"]

async def fetch_instagram_mentions(accounts=CURATED_ACCOUNTS) -> list[RawMention]
```

Key gotchas:
- Scrapes public profile JSON (`window._sharedData`) via `httpx` — no Selenium. Fragile but sufficient as supplementary source
- On failure, log and continue — must not block the seed job
- These accounts should exist as `is_curated=True` rows in `sources` table for the score boost

---

### `backend/crawler/place_resolver.py`
**Purpose:** Resolves free-text place mention → canonical Google `place_id` via LLM + fuzzy match.

```python
async def resolve_place(
    raw_text: str, location_lat: float, location_lng: float,
    similarity_threshold: float = 0.85,
    distance_threshold_m: int = 300
) -> ResolvedPlace | None
```

Sequence:
1. `gpt-4o-mini` extracts place name from `raw_text` (cheap call, JSON output: `{place_name: str | null}`)
2. Google Places Text Search: `"{place_name} cafe coffee NYC"` with location bias
3. For each result: `difflib.SequenceMatcher` similarity > 0.85 AND haversine distance < 300m
4. Return best match or `None`

Key gotchas:
- Cache resolved `place_id`s in-memory per crawl run (dict keyed by place_name) — same cafe appears in many posts
- On zero results, retry without location bias for well-known chains
- Use `gpt-4o-mini` here, `gpt-4o` only in `llm_extractor.py`

---

### `backend/crawler/llm_extractor.py`
**Purpose:** Uses GPT to extract structured WFH attributes + confidence scores from raw text.

```python
async def extract_wfh_attributes(raw_text: str, place_name: str) -> ExtractionResult

class ExtractionResult(BaseModel):
    has_wifi: bool | None; has_outlets: bool | None; is_laptop_friendly: bool | None
    noise_level: Literal['quiet','moderate','loud'] | None; seating_comfort: str | None
    wifi_confidence: float; outlet_confidence: float
    noise_confidence: float; laptop_confidence: float
    evidence_snippet: str | None  # direct quote from raw_text, stored in UI
```

Prompt: system = strict extractor, return null for unmentioned attrs, confidence 0.0 if not mentioned. `temperature=0`. Truncate `raw_text` to 800 chars. Use `gpt-4o-mini` (not `gpt-4o` — ~$0.04/region crawl vs ~$0.40).

Key gotcha: `evidence_snippet` must be a direct quote — the LLM must not hallucinate it since it's displayed to users.

---

### `backend/crawler/db_writer.py`
**Purpose:** All Supabase writes from the crawler: places, mentions, sources, post-crawl boolean attrs.

Key functions:
```python
async def ensure_source_exists(platform, handle_or_domain, is_curated) -> str  # source_id
# UPSERT sources ON CONFLICT (platform, handle_or_domain) DO NOTHING, then SELECT id

async def write_place_and_mention(resolved, region_id, source_id, extraction, raw_mention) -> None
# 1. UPSERT places ON CONFLICT (place_id) DO UPDATE SET last_enriched_at=now()
#    (do NOT touch wfh_score — trigger owns it)
# 2. INSERT INTO mentions ON CONFLICT (url) DO NOTHING
#    [DB trigger fires: recomputes wfh_score, mention_count, source_count]

async def recompute_boolean_attrs_for_region(region_id: str) -> None
# Majority-vote aggregation via single SQL query (conditional aggregation, not Python-side)
# BATCH UPDATE places SET has_wifi=?, has_outlets=?, is_laptop_friendly=?, noise_level=?
```

Key gotchas:
- `recompute_boolean_attrs` must use SQL conditional aggregation (`SUM(CASE WHEN wifi_confidence > 0.5 THEN 1 ELSE 0 END)`) — do not pull rows to Python
- UPSERT for `places` must NOT overwrite `wfh_score` — trigger-owned
- `ensure_source_exists` must use `ON CONFLICT DO NOTHING` — concurrent crawlers can race here

---

## Layer 5: Next.js Frontend

### `coffee-map/app/page.tsx`
**Purpose:** Root page — thin shell that renders `<Header />` and `<MapContainer />`. No state here.

Key gotcha: No `use client` here — let `MapContainer` declare it. Keep this file under 20 lines.

---

### `coffee-map/app/layout.tsx`
**Purpose:** Root layout — sets up HTML shell and Google Maps script loading.

Use `@next/third-parties` `GoogleMapsScript` component for Maps JS API loading (handles Next.js hydration). The Maps API key here is PUBLIC (browser key with HTTP referrer restrictions). Backend uses a separate server-side key.

---

### `coffee-map/app/api/places/route.ts`
**Purpose:** Proxies `POST /nearby-search` from browser to FastAPI. Hides backend URL from client.

```typescript
export async function POST(request: Request): Promise<Response>
// fetch(`${process.env.BACKEND_URL}/places/nearby-search`, { method:'POST', cache:'no-store', body })
```

Key gotcha: `BACKEND_URL` is server-only (no `NEXT_PUBLIC_` prefix). `cache: 'no-store'` prevents Next.js from caching map responses.

---

### `coffee-map/app/api/places/[place_id]/mentions/route.ts`
**Purpose:** Proxies `GET /places/{place_id}/mentions` to FastAPI.

```typescript
export async function GET(request: Request, { params }: { params: { place_id: string } }): Promise<Response>
```

---

### `coffee-map/components/map/MapContainer.tsx`
**Purpose:** Central `"use client"` component. Owns the Google Maps instance, all map state, and orchestrates data fetching on pan.

Key structure:
```typescript
const mapRef = useRef<google.maps.Map | null>(null)
const [selectedPlaceId, setSelectedPlaceId] = useState<string | null>(null)
const { bounds } = useMapBounds(mapRef)
const { places, regionStatus } = usePlaces(bounds)
// Renders: PlacePins, InfoCard (if selectedPlaceId), ColdRegionBanner (if cold)
```

Key gotchas:
- Initialize `new google.maps.Map(...)` in `useEffect`, guard `window.google?.maps`
- NYC default center: `{ lat: 40.7128, lng: -74.0060 }`, zoom: 13
- Use `AdvancedMarkerElement` (modern API) for pins — requires `mapId` set on Map init (create in Google Cloud Console)
- Do not use `@googlemaps/react-wrapper` — plain `useRef` + `useEffect` is simpler with App Router

---

### `coffee-map/hooks/useMapBounds.ts`
**Purpose:** Attaches debounced `bounds_changed` listener to the Maps instance; returns current `MapBounds`.

800ms debounce. Returns `null` before map loads — `usePlaces` must handle `null` gracefully. Cleanup via `google.maps.event.removeListener(listener)`.

---

### `coffee-map/hooks/usePlaces.ts`
**Purpose:** Fetches `PlacePin[]` from `/api/places` whenever bounds changes. Handles abort on new pan.

```typescript
export function usePlaces(bounds: MapBounds | null): { places: PlacePin[], regionStatus: string | null, isLoading: boolean }
```

Key gotchas:
- `AbortController` per fetch — abort on every new bounds change to prevent stale-response pin flicker
- Use `JSON.stringify(bounds)` as the `useEffect` dep key to avoid infinite loops from object reference changes

---

### `coffee-map/hooks/useMentions.ts`
**Purpose:** Fetches `MentionCard[]` for a `place_id` when a pin is clicked.

```typescript
export function useMentions(placeId: string | null): { mentions: MentionCard[], isLoading: boolean }
```

---

### `coffee-map/components/map/InfoCard.tsx`
**Purpose:** Side panel shown on pin click — place details, attribute pills, mention cards.

Props: `{ placeId: string, place: PlacePin, onClose: () => void }`. Renders static place data immediately; mentions load async via `useMentions(placeId)`. Fixed overlay on mobile (bottom sheet), side panel on desktop via Tailwind responsive classes.

---

### `coffee-map/components/map/AttributePills.tsx`
**Purpose:** Renders WFH attribute pills from a `PlacePin`.

Key gotcha: Render `null` for unknown attrs — do NOT show "unknown" pills. Noise level pill colors: quiet=green, moderate=yellow, loud=red.

---

### `coffee-map/components/ui/MentionCard.tsx`
**Purpose:** One mention row: `[Platform] handle  "evidence snippet" [↗]`

Key gotcha: `evidence_snippet` can be null — show "Mentioned this place" fallback, not an empty element. External link: `target="_blank" rel="noopener noreferrer"`.

---

### `coffee-map/components/map/PlacePin.tsx`
**Purpose:** `AdvancedMarkerElement` wrapper for a single enriched place pin.

Pin colors: `wfh_score >= 8.0` → green, `wfh_score >= 6.0` → amber. Cleanup: `marker.map = null` on unmount.

Key gotcha: `AdvancedMarkerElement` requires `mapId` on the Map instance at init time — without it, throws at runtime.

---

### `coffee-map/components/map/ColdRegionBanner.tsx`
**Purpose:** Non-blocking notification when a cold region is detected.

Auto-dismiss after 8 seconds. Message: "Discovering coffee shops in this area... check back soon." Must NOT imply the user should wait — it's a background process.

---

### `coffee-map/components/ui/PlatformPill.tsx`
**Purpose:** Color-coded platform badge.

```typescript
const PLATFORM_COLORS: Record<Platform, string> = {
  reddit: 'bg-orange-500 text-white',
  instagram: 'bg-pink-500 text-white',
  blog: 'bg-blue-500 text-white',
  tiktok: 'bg-black text-white',
  google_review: 'bg-green-500 text-white',
}
```

---

### `coffee-map/lib/api-client.ts`
**Purpose:** Centralized fetch helpers with error handling for hooks.

```typescript
export async function fetchNearbyPlaces(req: NearbySearchRequest, signal?: AbortSignal): Promise<NearbySearchResponse>
export async function fetchMentions(placeId: string, signal?: AbortSignal): Promise<MentionsResponse>
```

On 4xx/5xx: return empty state (empty places, null region_status) — do not throw. Map degrades gracefully.

---

### `coffee-map/lib/map-utils.ts`
**Purpose:** Pure utility functions for map geometry.

```typescript
export function boundsToCenter(bounds: MapBounds): { lat: number; lng: number }
export function haversineDistanceMeters(lat1, lng1, lat2, lng2): number
export function boundsOverlap(a: MapBounds, b: MapBounds): boolean
```

---

### `coffee-map/next.config.ts`
Key gotcha: Only `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` is public. `BACKEND_URL` is server-only.

---

## Environment Variables (`.env.example`)

```bash
# Frontend (public)
NEXT_PUBLIC_GOOGLE_MAPS_API_KEY=   # Browser Maps JS API, restrict by HTTP referrer

# Frontend (server-only)
BACKEND_URL=                        # FastAPI backend URL, never exposed to browser

# Backend
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=          # Service role — bypasses RLS, never log
GOOGLE_PLACES_API_KEY=              # Separate from browser key; restrict by Render IP
OPENAI_API_KEY=
TAVILY_API_KEY=
BRAVE_SEARCH_API_KEY=               # Brave Web Search API subscription token
YELP_API_KEY=                       # Yelp Fusion API key (free tier: 500 calls/day)
FRONTEND_URL=                       # For CORS allow_origins

# Tunable thresholds (optional, have defaults)
PIN_SCORE_THRESHOLD=6.0
PIN_LAPTOP_CONFIDENCE_THRESHOLD=0.7
NEARBY_SEARCH_RADIUS_METERS=1500
PLACE_RESOLVER_SIMILARITY_THRESHOLD=0.85
PLACE_RESOLVER_DISTANCE_THRESHOLD_METERS=300
```

Two separate Google API keys: browser key has HTTP referrer restrictions; server key has IP restrictions (Render's outbound IP). Never share one key between both.

---

## Implementation Order

1. **Supabase migrations** (001 → 002 → 003) + seed file — nothing works without the DB
2. **`backend/config.py` + models** — foundation for all backend code
3. **`supabase_client.py` + `google_places.py`** — the two external service wrappers everything depends on
4. **`region_detector.py` + `place_filter.py`** — core hot-path logic
5. **`routers/places.py` + `routers/mentions.py`** — the two routes the frontend calls
6. **Next.js types + API routes + hooks** — frontend data layer
7. **`MapContainer` + `PlacePin` + `InfoCard`** — UI rendering
8. **Crawler pipeline** (orchestrator → sources → resolver → extractor → writer) — independently testable
9. **Manhattan seed run** — run crawler against Manhattan only before launch; other boroughs are Phase 2 (commented out in seed SQL, blocked by `ALLOWED_CITY_SLUGS` guardrail in orchestrator)
10. **`scheduler.py`** — Phase 1 optional, add after MVP is stable
11. **README updates** — rewrite root `README.md`, `backend/README.md` (if present), and `coffee-map/README.md` to reflect V2 architecture: new directory structure, V2 data flow, updated env var list, deployment instructions for Render + Vercel + Supabase, and how to run the crawler manually

---

## Verification

- **Supabase trigger:** Insert a test mention row directly in SQL; confirm `wfh_score`, `mention_count`, `source_count` recompute on the parent `places` row
- **Hot path:** `POST /places/nearby-search` with NYC bounds — confirm response time < 300ms, no enrichment triggered
- **Cold region:** Clear region status to `cold`, pan map, confirm: response returns immediately with `region_status='cold'`, no pins, `ColdRegionBanner` shows and auto-dismisses in 8s, region flips to `crawling` in Supabase
- **Pin eligibility filter:** Insert a place with `wfh_score=5.9` — confirm it never appears as a pin
- **Mention dedup:** Insert same URL twice — confirm second insert is silently ignored (ON CONFLICT DO NOTHING), `mention_count` stays at 1
- **Pin click:** Click a pin, confirm `InfoCard` renders static data immediately, mentions load asynchronously
- **`AdvancedMarkerElement`:** Confirm `mapId` is set on Map init; pins render without console errors
