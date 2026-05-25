# BrewDesk

**Find your next workspace between meetings.**

A map that shows WFH-friendly coffee shops, cafes, and libraries in Manhattan. Every pin is backed by real web mentions (Reddit, blogs, Instagram), and its dynamically updated to account for changes in the location. 

Users can see wifi/outlets/noise level attributes and read the actual sources that mentioned the place.

**Target user:** NYC knowledge workers who need a spot to work between back-to-back meetings and want something better than "coffee shop near me."

The data curated is fundamentally different from Google reviews — it's editorial and social, not star ratings. We're pulling signals from blogs, subreddits, Instagram accounts to keep it recent, relevant, and interesting.

---
 
## Current architecture
 
### Tech stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js, TypeScript |
| Map | Google Maps API, NearbySearch + TextSearch |
| Backend | FastAPI, Python |
| Database | Supabase (Postgres) |
| Web search | Tavily API, Brave Search API |
| LLM | OpenAI |
| Hosting | Frontend: Vercel · Backend: Render |

---
 
**How it works:** A background crawler pre-populates the DB with enriched places. When a user pans the map, the backend queries Supabase. Pins only appear for places that have real web mentions and a mapped google location.
 
---

## How it works (high level)

V1 ran expensive web scraping and LLM enrichment inline with every map pan. Every user request triggered Tavily searches and GPT calls, making the app slow and redundant.

V2 flips the model: the map is a **read-only view into a pre-built, enriched database**. All expensive work happens offline in a background crawler pipeline before any user ever touches the map. When a user pans, the backend just queries Supabase.

```
┌─────────────────────────────────────────────────────────┐
│  OFFLINE (background, runs once per region)             │
│                                                         │
│  Web Sources → Place Resolver → LLM Extractor → DB      │
│  (Tavily, Brave, Instagram)    (GPT-4o-mini)            │
└─────────────────────────────────────────────────────────┘
                          ↓ pre-built enriched DB
┌─────────────────────────────────────────────────────────┐
│  ONLINE (per map pan, ~200ms)                           │
│                                                         │
│  User pans → Google Nearby Search → filter by DB →      │
│  merge Google metadata → render red pins instantly       │
└─────────────────────────────────────────────────────────┘
```

---

## Architecture detail

### Stage 1 — Map pan (read path)

Every time the user pans or zooms the map, the frontend fires a debounced request to the backend with the current viewport bounds.

**What happens:**

1. `MapContainer.tsx` detects bounds change via `useMapBounds` hook
2. `usePlaces` hook POSTs `{lat, lng, bounds}` to `Next.js /api/places`
3. Next.js proxies to `FastAPI POST /places/nearby-search`
4. FastAPI fires two requests **in parallel**:
   - **Google Nearby Search** — 3 concurrent requests (cafe, bakery, library) returning up to 60 place IDs, plus photos, rating, review count, type, and opening hours
   - **Region detection** — checks if the viewport overlaps a known region and whether it's `cold`, `crawling`, or `seeded`
5. FastAPI filters the Google place IDs against the `places` table in Supabase — only places that have been crawler-validated are returned
6. Google metadata (photos, rating, hours) is merged into the response live, and saved to the DB in a background task
7. If the region is `cold` (never crawled), a background seed job is triggered and the map shows no pins while crawling runs

**Result:** Enriched pins appear in ~200ms. No LLM calls in the hot path.

---

### Stage 2 — Pin info card (on click)

When a user clicks a red pin, the `InfoCard` panel slides up showing:

- **Photos** — horizontal scroll strip from Google Places
- **Type chip** — e.g. "Cafe", "Bakery"
- **Star rating** — Google rating + review count
- **Open in Google Maps link** — deep-links to the place's Google Maps page
- **Today's hours** — pulled from `regularOpeningHours.weekdayDescriptions`
- **WFH attributes** — wifi, outlets, noise level (majority-voted from crawl data)
- **Mention cards** — each web source that mentioned the place, with evidence snippet, platform, and confidence score

Mention data loads async (`useMentions` hook → `GET /api/places/{place_id}/mentions`) so the card renders immediately with static data.

---

### Stage 3 — Offline crawler pipeline (write path)

The crawler runs once per region (triggered when a region transitions `cold → crawling`). It is the only thing that writes to the `places` and `mentions` tables.

**Phase 1 — Source collection**

Three sources are queried sequentially to avoid overwhelming the Google Places Text Search rate limit:

| Source | What it fetches |
|--------|----------------|
| **Tavily** | AI-powered web search across blogs, Reddit, Yelp, nymag, timeout, etc. Uses 1 best query per city, extracts up to 5 URLs |
| **Brave Search** | Fallback web search, catches sources Tavily missed |
| **Instagram** | Scrapes curated accounts known to post Manhattan WFH spots |

URLs are deduplicated across phases via a `seen_urls` set.

**Phase 2 — Place resolution**

For each raw mention, a two-step resolver maps free-text to a canonical Google `place_id`:

1. `gpt-4o-mini` extracts the place name from the raw text
2. Google Places Text Search finds candidates near the region center
3. `difflib.SequenceMatcher` fuzzy-matches the extracted name against candidates (threshold: 0.65 similarity)
4. Distance check ensures the match is within 25km of the region center (covers all of Manhattan)

If no place is resolved, the mention is still saved to the `mentions` table with `place_id = NULL`. This "unmatched mention cache" allows future pairing when new regions are seeded — mentions won't be re-scraped or re-extracted.

**Phase 3 — LLM extraction**

`gpt-4o-mini` reads the raw text and extracts four WFH confidence scores (0.0–1.0):

- `wifi_confidence` — evidence of wifi
- `outlet_confidence` — evidence of power outlets
- `noise_confidence` — evidence of a loud/noisy environment
- `laptop_confidence` — evidence of laptop-friendly vibe

Plus an `evidence_snippet` — a direct quote from the source shown in the UI.

**Phase 4 — DB write**

For matched mentions:
1. `UPSERT places` — inserts or updates the place row (never touches `wfh_score`, which is trigger-owned)
2. `INSERT INTO mentions ON CONFLICT (url) DO NOTHING` — idempotent; the unique URL constraint deduplicates across crawl runs
3. A Postgres trigger fires after each insert and recomputes `wfh_score`, `mention_count`, `source_count` on the parent place

For unmatched mentions: saved with `place_id = NULL`, trigger skips them.

After all mentions are written, a majority-vote pass computes boolean WFH attributes (`has_wifi`, `has_outlets`, `is_laptop_friendly`, `noise_level`) for each place in the region.

**wfh_score formula:**
```
wfh_score = (avg_wifi × 2.5) + (avg_outlet × 2.0) + (avg_noise × 2.0)
          + (avg_laptop × 3.5) + curated_boost (capped at +2.0)
```
Scale is 0–10. Curated sources (Instagram accounts we hand-picked) add a 0.5 bonus per source.

---

### Stage 4 — Region system

Regions are named bounding boxes (Manhattan = `nyc-manhattan`). Each has a status:

| Status | Meaning |
|--------|---------|
| `cold` | Never crawled — triggers background seed on first map pan |
| `crawling` | Seed job is actively running — map shows no pins |
| `seeded` | Crawl complete — pins appear on next map pan |

The `cold → crawling` transition is atomic (conditional UPDATE on `status = 'cold'`) to prevent two concurrent requests from double-triggering a crawl.

---

## Database schema

Four normalized Supabase tables:

```
regions       — bounding boxes with crawl status
places        — canonical enriched places (Google place_id as PK)
sources       — web sources (subreddit, Instagram account, blog domain)
mentions      — individual mentions linking source → place (or NULL for unmatched)
```

`places` is the read-heavy table. Key columns:

| Column | Owner | Notes |
|--------|-------|-------|
| `wfh_score` | DB trigger | Recomputed on every mention insert |
| `mention_count` | DB trigger | Count of mentions with non-null place_id |
| `source_count` | DB trigger | Distinct sources |
| `has_wifi`, `has_outlets`, `is_laptop_friendly`, `noise_level` | `db_writer` | Majority-vote after full crawl |
| `photos` | `routers/places.py` | Saved from Google Nearby Search response |
| `primary_type`, `rating`, `user_rating_count`, `regular_opening_hours` | `routers/places.py` | Saved from Google Nearby Search response |

---

## Running locally

**Terminal 1 — Backend**
```bash
source .venv/bin/activate
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```
Requires `backend/.env.local` with: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_PLACES_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`, `BRAVE_SEARCH_API_KEY`, `FRONTEND_URL=http://localhost:3000`

**Terminal 2 — Frontend**
```bash
cd coffee-map
npm install
npm run dev
```
Requires `coffee-map/.env.local` with: `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`, `NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID`, `BACKEND_URL=http://localhost:8000`

Open `http://localhost:3000`.

**Trigger a crawl manually**
runs the full pipeline (web crawl → place resolver → enrich)
```bash
curl -X POST -H "X-Admin-Key: random-secret-admin-key" http://localhost:8000/regions/{region_id}/seed
```
example region_id = 65be0415-597d-40e1-89e4-a63f6e6c8e97


**Trigger enriching the google places details for existing places**
curl -X POST "http://localhost:8000/regions/{region_id}" -H "X-Admin-Key: random-secret-admin-key"

---

## Adding a new city or region

Regions are **not** auto-created from map panning. The frontend only triggers a crawl for regions that already exist in the database with `status = 'cold'`. Follow these steps to add a new city:

### Step 1 — Add the slug to the allowed list

In `backend/crawler/orchestrator.py`, add the new slug to `ALLOWED_CITY_SLUGS`:

```python
ALLOWED_CITY_SLUGS = {
    "nyc-manhattan",
    "nyc-queens",
    "my-new-city",   # add here
}
```

### Step 2 — Add the display name for search queries

In `backend/crawler/sources/tavily_crawler.py`, add an entry to `SLUG_DISPLAY`:

```python
SLUG_DISPLAY: dict[str, tuple[str, str]] = {
    ...
    "my-new-city": ("City Name", "Neighborhood or City Name"),
}
```

The tuple is `(city, area)` — both are substituted into the search query templates. For city-wide regions with no specific neighborhood, use the city name for both (e.g. `("Chicago", "Chicago")`).

### Step 3 — Insert a row in Supabase

The region row defines the bounding box the crawler and map detector use. Run this SQL in the Supabase SQL editor (Table Editor → SQL):

```sql
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('my-new-city', 'cold', <min_lat>, <max_lat>, <min_lng>, <max_lng>)
ON CONFLICT (city_slug) DO NOTHING;
```

To find bounding box coordinates: open Google Maps, draw a rectangle around the area, and read off the lat/lng corners. Alternatively use [bboxfinder.com](http://bboxfinder.com).

The bounding box determines:
- Which viewport pans trigger a seed job for this region
- The center point used by the place resolver (25km radius for candidate matching)

### Step 4 — Also update `seed.sql`

Add the same INSERT to `backend/supabase/seed.sql` so future `supabase db reset` runs include the new region automatically.

### Step 5 — Trigger the crawl

Once the DB row exists, panning the map over the region will automatically kick off the seed job (the frontend detects `status = 'cold'` and triggers it). You'll see the expansion banner appear.

To trigger manually without a map pan:
```bash
# 1. Get the region_id from Supabase (regions table)
# 2. Run:
curl -X POST -H "X-Admin-Key: <your-admin-key>" http://localhost:8000/regions/{region_id}/seed
```

Pins will start appearing within ~3–5 minutes as the resolver processes mentions.
