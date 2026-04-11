# V2 WFH Coffee Shop Finder — Sequence Diagram

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant FE as Frontend
  participant NX as Next.js API
  participant FA as FastAPI
  participant SB as Supabase
  participant GP as Google Places
  participant CR as Crawler

  rect rgb(230, 241, 251)
    Note over U,NX: 1 — location permission
    U->>FE: grants location permission
    FE->>NX: GET /api/places?bounds=...
  end

  rect rgb(225, 245, 238)
    Note over FE,GP: 2 — map pan: nearby search + region check
    FE->>NX: pan/zoom event (debounced 800ms)
    NX->>FA: POST /nearby-search {lat, lng, bounds}
    FA->>GP: Nearby Search API (parallel by type)
    GP-->>FA: 20 raw place_ids + metadata
    FA->>SB: check region status
    SB-->>FA: seeded or cold
    FA->>SB: filter place_ids against places table
    SB-->>FA: matched places + wfh_score + source_count
  end

  rect rgb(250, 238, 218)
    Note over U,SB: 3 — DB filter + immediate pin render
    FA-->>NX: enriched places (DB-matched only)
    NX-->>FE: places with wfh_score, attrs, source_count
    FE-->>U: render enriched pins instantly
    FE-->>U: no pins shown if cold region
  end

  rect rgb(250, 236, 231)
    Note over FA,CR: 4 — cold region: background seed trigger
    FA-)SB: set region status = crawling
    FA-)CR: enqueue seed job {region_id, bounds}
    FA-->>FE: region=cold, no pins (non-blocking)
  end

  rect rgb(230, 241, 251)
    Note over U,SB: 5 — user clicks pin: fetch mention detail
    U->>FE: clicks map pin
    FE->>NX: GET /api/places/{place_id}/mentions
    NX->>FA: GET /places/{place_id}/mentions
    FA->>SB: SELECT mentions JOIN sources ORDER BY confidence
    SB-->>FA: mentions[] {url, snippet, platform, handle}
    FA-->>FE: mention cards + source buttons
    FE-->>U: show pin info card
  end

  rect rgb(225, 245, 238)
    Note over GP,CR: 6 — offline crawler pipeline (scheduled/async)
    CR->>GP: Text Search to resolve place name to place_id
    GP-->>CR: place_id + match confidence
    Note over CR: LLM extracts WFH attrs from raw content
    CR->>SB: UPSERT places (place_id, wfh attrs, score)
    CR->>SB: INSERT mentions ON CONFLICT (url) DO NOTHING
    Note over SB: DB trigger recomputes wfh_score, mention_count, source_count
    CR->>SB: UPDATE regions SET status = seeded
    Note over SB,FE: next map pan finds status=seeded — pins appear
  end
```

## Arrow key

| Syntax | Meaning |
|--------|---------|
| `->>`  | Synchronous call |
| `-->>` | Response / return |
| `-)`   | Async fire-and-forget |