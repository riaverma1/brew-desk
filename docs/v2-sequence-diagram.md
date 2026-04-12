# V2 WFH Coffee Shop Finder — Sequence Diagram

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant FE as Frontend
  participant NX as Next.js API
  participant FA as FastAPI
  participant SB as Supabase
  participant GP as Google Places API
  participant CR as Crawler

  %% ─── Map load / pan ───────────────────────────────────────
  rect rgb(225, 245, 238)
    Note over U,GP: 1 — map pan: nearby search + region check (parallel)
    U->>FE: pans or zooms map
    FE->>NX: POST /api/places {lat, lng, bounds} (debounced 800ms)
    NX->>FA: POST /places/nearby-search {lat, lng, bounds}
    par Google Nearby Search (3 concurrent types)
      FA->>GP: searchNearby type=cafe
      FA->>GP: searchNearby type=bakery
      FA->>GP: searchNearby type=library
      GP-->>FA: place_ids + photos + rating + primaryType + regularOpeningHours
    and Region status check
      FA->>SB: SELECT regions WHERE bounds overlap viewport
      SB-->>FA: region_id + status (cold / crawling / seeded)
    end
  end

  %% ─── DB filter + pin render ────────────────────────────────
  rect rgb(250, 238, 218)
    Note over FA,FE: 2 — filter + enrich + render
    FA->>SB: SELECT places WHERE place_id IN (...) [crawler-validated only]
    SB-->>FA: matched places with wfh_score, WFH attrs, mention_count
    Note over FA: merge Google metadata into response<br/>(photos, rating, type, hours override stale DB values)
    FA-)SB: UPDATE places SET photos/rating/type/hours (background)
    FA-->>NX: NearbySearchResponse {places[], region_status, region_id}
    NX-->>FE: enriched places
    FE-->>U: render red pins instantly
  end

  %% ─── Cold region seed ──────────────────────────────────────
  rect rgb(250, 236, 231)
    Note over FA,CR: 3 — cold region: trigger background crawl (non-blocking)
    FA-)SB: UPDATE regions SET status=crawling WHERE status=cold
    FA-)CR: background_tasks.add_task(trigger_seed, region_id)
    FA-->>FE: region_status=cold, places=[] (returns immediately)
    FE-->>U: show "Discovering spots…" banner, no pins yet
  end

  %% ─── Pin click / info card ─────────────────────────────────
  rect rgb(230, 241, 251)
    Note over U,SB: 4 — user clicks pin: fetch mention detail
    U->>FE: clicks red pin
    Note over FE: InfoCard renders immediately with:<br/>photos · rating · primaryType · today's hours<br/>WFH attribute pills · "Open in Google Maps" link
    FE->>NX: GET /api/places/{place_id}/mentions
    NX->>FA: GET /places/{place_id}/mentions
    FA->>SB: SELECT mentions JOIN sources ORDER BY laptop_confidence DESC LIMIT 20
    SB-->>FA: mentions[] {url, snippet, platform, handle, confidence scores}
    FA-->>FE: mention cards
    FE-->>U: mention cards load in (source snippets, platform, link)
  end

  %% ─── Crawler pipeline ──────────────────────────────────────
  rect rgb(225, 245, 238)
    Note over CR,SB: 5 — offline crawler pipeline (async, runs once per region)

    Note over CR: Phase 1 — collect raw mentions
    CR->>CR: Tavily web search (1 best query → up to 5 URLs)
    CR->>CR: Brave Search (fallback coverage)
    CR->>CR: Instagram scrape (curated accounts)
    Note over CR: deduplicate URLs across all sources

    Note over CR: Phase 2 — resolve place name → place_id
    loop for each raw mention
      CR->>CR: gpt-4o-mini extracts place name from raw text
      CR->>GP: Text Search (place name + location bias)
      GP-->>CR: candidate place_ids with name + coords
      CR->>CR: fuzzy match (difflib ≥ 0.65) + distance check (≤ 25km)
      alt place resolved
        CR->>CR: gpt-4o-mini extracts WFH confidence scores + evidence snippet
        CR->>SB: UPSERT places (name, lat, lng, region_id) — never touches wfh_score
        CR->>SB: INSERT INTO mentions (place_id, scores, snippet, url) ON CONFLICT (url) DO NOTHING
        Note over SB: DB trigger fires → recomputes wfh_score,<br/>mention_count, source_count on parent place
      else no match
        CR->>CR: gpt-4o-mini still extracts WFH scores (for future pairing)
        CR->>SB: INSERT INTO mentions (place_id=NULL, scores, url) ON CONFLICT DO NOTHING
        Note over SB: trigger skips NULL place_id rows<br/>unmatched mentions cached for future region expansion
      end
    end

    Note over CR: Phase 3 — post-crawl boolean attribute vote
    CR->>SB: majority-vote wifi/outlets/laptop/noise per place (SQL aggregation)
    CR->>SB: UPDATE regions SET status=seeded
    Note over SB,FE: next map pan finds status=seeded → DB-matched pins appear
  end
```

## Arrow key

| Syntax | Meaning |
|--------|---------|
| `->>`  | Synchronous call (caller waits) |
| `-->>` | Response / return value |
| `-)`   | Async fire-and-forget (non-blocking) |
| `par`  | Parallel execution block |
| `loop` | Repeats for each item |
| `alt`  | Conditional branch |
