---
name: Restructure enrichment for latency and cost reduction
overview: Restructure the enrichment flow to return basic info immediately from nearby_search, then asynchronously score and select top-5 places for full enrichment. Add ad-hoc enrichment endpoint for user-triggered enrichment.
todos:
  - id: extract_basic_info
    content: Create extract_basic_info_from_nearby_search() function to extract place object from nearby_search result
    status: pending
  - id: save_basic_info
    content: Create save_basic_info_to_json() function to save basic info immediately with nearby_search_flag
    status: pending
    dependencies:
      - extract_basic_info
  - id: scoring_module
    content: Create top_n_scoring.py module with rating_score, popularity_score, distance_score, wfh_type_score, and score_place functions
    status: pending
  - id: top_n_selection
    content: Create select_top_n_places() function that scores all places and returns top-5 place_ids
    status: pending
    dependencies:
      - scoring_module
  - id: modify_place_details
    content: Modify enrich_place_details_sync() to reuse basic info from nearby_search and fetch reviews + binary attributes (restroom, servesCoffee, outdoorSeating, goodForGroups, accessibilityOptions, parkingOptions, ServesCoffee)
    status: pending
    dependencies:
      - extract_basic_info
  - id: modify_async_enrichment
    content: Modify enrich_place_web_async() to wait for both place_details and Tavily to complete before LLM, handle partial evidence cases with appropriate flags
    status: pending
    dependencies:
      - modify_place_details
  - id: modify_endpoint
    content: Modify /nearby-search endpoint to save basic info immediately, return results immediately, and trigger background scoring+enrichment (place_details + Tavily in parallel, then LLM)
    status: pending
    dependencies:
      - save_basic_info
      - top_n_selection
      - modify_async_enrichment
  - id: ad_hoc_endpoint
    content: Add POST /api/places/enrich/{place_id} endpoint for user-triggered enrichment (runs place_details + Tavily in parallel, then LLM, handles partial evidence)
    status: pending
    dependencies:
      - modify_place_details
      - modify_async_enrichment
  - id: frontend_enrich_button
    content: Add 'Enrich' button to frontend for places without enriched_flag, calling new ad-hoc endpoint. Ensure 'Open in Google Maps' button still exists.
    status: pending
    dependencies:
      - ad_hoc_endpoint
---

# Restructure Enrichment for Latency and Cost Reduction

## Current Flow Issues

- All places get sync enrichment (place_details) immediately, blocking response
- All places get async enrichment (Tavily + LLM), wasting API calls on irrelevant places
- High latency due to waiting for sync enrichment before returning results

## New Flow

### Synchronous Response (Immediate)

1. Run `nearby_search` for all requested types
2. Extract basic info from nearby_search results (photos, ratings, types, open hours, binary attributes)
3. Save basic info to JSON immediately (creates/updates place entries with `nearby_search_flag`)
4. Return basic info to frontend immediately (no waiting for enrichment)

### Asynchronous Background Processing

1. Score all candidates from nearby_search using scoring functions
2. Select top-5 places based on scores
3. For top-5 only: run full enrichment (place_details for reviews + Tavily + LLM)
4. Update JSON with enriched data and flags

### Ad-hoc Enrichment

- Add endpoint `/api/places/enrich/{place_id}` for user-triggered enrichment
- Frontend shows "Enrich" button for places without `enriched_flag`
- Only enriches if not already in top-5 or already enriched

## Implementation Details

### 1. Create Basic Info Extraction Function

**File**: `backend/enrichment/places_manager.py`

- New function: `extract_basic_info_from_nearby_search(nearby_result: Dict) -> Dict`
- Extracts ONLY: name, photos (processed), rating, user_ratings_total, types, regular_opening_hours, price_level, website, neighborhood, business_status, formatted_address, lat, lng
- **DO NOT** include binary attributes here (restroom, servesCoffee, etc.) - those come later from place_details
- Returns place object structure matching existing format
- Note: Frontend must preserve "Open in Google Maps" button functionality

### 2. Create Basic Info Save Function

**File**: `backend/enrichment/places_manager.py`

- New function: `save_basic_info_to_json(nearby_results: List[Dict], json_path: str) -> List[str]`
- For each nearby_result:
- Extract basic info using function above
- Upsert place_id if needed
- Update place object with basic info
- Set `nearby_search_flag = True` (new flag)
- Set `places_details_flag = False` (not yet enriched)
- Save to JSON

### 3. Create Scoring Module

**File**: `backend/enrichment/top_n_scoring.py` (new file)

- Implement scoring functions:
- `rating_score(rating: float) -> float` - 3.5 -> 0.0, 5.0 -> 1.0 (clamped)
- `popularity_score(user_ratings_total: int, max_reviews_in_viewport: int) -> float` - uses log to diminish returns
- `distance_score(distance_m: float, max_radius_m: float) -> float` - closer is better
- `wfh_type_score(types: list[str]) -> float` - uses WFH_TYPE_PRIORS dict
- New function: `score_place(place: Dict, user_lat: float, user_lng: float, max_radius_m: float, max_reviews: int) -> float`
- Combines all scores with weights
- Returns total score

### 4. Create Top-N Selection Function

**File**: `backend/enrichment/places_manager.py`

- New function: `select_top_n_places(places: List[Dict], user_lat: float, user_lng: float, max_radius_m: float, n: int = 5) -> List[str]`
- Scores all places
- Sorts by score descending
- Returns top-n place_ids
- Filters out places already enriched (`enriched_flag = True`)

### 5. Modify Place Details Enrichment (Now Async)

**File**: `backend/enrichment/place_enrichment.py`

- **Note**: `enrich_place_details_sync` will now run asynchronously (in background for top-5, or immediately for user-triggered)
- Modify `enrich_place_details_sync` to:
- Check if basic info already exists from nearby_search
- If yes, reuse basic info and only fetch from place_details:
- **Reviews** (for LLM derivation)
- **Binary attributes**: restroom, servesCoffee, outdoorSeating, goodForGroups, accessibilityOptions, parkingOptions, ServesCoffee
- Merge reviews and binary attributes into existing place object
- Don't overwrite basic info that's already there
- Set `places_details_flag = True` after successful fetch

### 6. Modify Nearby Search Endpoint

**File**: `backend/api/routes/places.py`

- Modify `/nearby-search` endpoint:
- Run nearby_search for all types
- Immediately save basic info to JSON (synchronous, but fast)
- Return basic info to frontend immediately
- Trigger background task for scoring + top-5 enrichment
- New background task: `score_and_enrich_top_n_background`
- Load places from JSON
- Score all places from nearby_search results
- Select top-5
- For top-5 places:
- Run place_details enrichment (async) - fetches reviews + binary attributes
- Run Tavily enrichment (async)
- **Wait for both to complete** before running LLM
- Run LLM derivation on all available evidence (Google reviews + Tavily)
- Handle partial evidence cases:
    - If place_details succeeds but Tavily fails: set `places_details_flag=True`, `tavily_flag=False`, `enriched_flag=True` (LLM uses only Google reviews)
    - If Tavily succeeds but place_details fails: set `places_details_flag=False`, `tavily_flag=True`, `enriched_flag=True` (LLM uses only Tavily)
    - If both succeed: set both flags to True, `enriched_flag=True`

### 7. Add Ad-hoc Enrichment Endpoint

**File**: `backend/api/routes/places.py`

- New endpoint: `POST /api/places/enrich/{place_id}`
- Check if place exists
- Check if already enriched (`enriched_flag = True`)
- If not enriched:
    - Run place_details enrichment (synchronous/immediate) - fetches reviews + binary attributes
    - Run Tavily enrichment (synchronous/immediate)
    - Wait for both to complete before running LLM
    - Run LLM derivation on all available evidence
    - Handle partial evidence cases (same logic as background task)
    - Return updated place data
- If already enriched, return existing data

### 8. Update Frontend

**File**: `coffee-map/app/page.tsx`

- Add "Enrich" button to place tooltips/info windows for places where `enriched_flag = False`
- Button calls new `/api/places/enrich/{place_id}` endpoint
- Show loading state while enriching
- Refresh place data after enrichment completes
- **Important**: Preserve existing "Open in Google Maps" button functionality - ensure it still works with basic info from nearby_search

### 9. Update JSON Schema

- Add `nearby_search_flag: bool` to track if basic info was saved from nearby_search
- Keep existing flags: `places_details_flag`, `tavily_flag`, `enriched_flag`

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant Frontend
    participant API as /nearby-search
    participant NearbySearch as nearby_search()
    participant BasicInfo as save_basic_info()
    participant JSON as JSON Storage
    participant Background as Background Task
    participant Scorer as scoring functions
    participant PlaceDetails as place_details()
    participant Tavily as Tavily API
    participant LLM as LLM Derivation

    Frontend->>API: POST /nearby-search (lat, lng)
    API->>NearbySearch: Search for all types
    NearbySearch-->>API: nearby_results[]
    API->>BasicInfo: Extract & save basic info
    BasicInfo->>JSON: Save place objects with nearby_search_flag=True
    API-->>Frontend: Return basic info immediately
    
    API->>Background: Trigger async task
    Background->>JSON: Load places
    Background->>Scorer: Score all places
    Scorer-->>Background: Scores[]
    Background->>Background: Select top-5
    par Parallel Enrichment
        Background->>PlaceDetails: Fetch reviews + binary attrs (top-5)
        Background->>Tavily: Web search (top-5)
    end
    PlaceDetails-->>Background: Reviews + binary attrs
    Tavily-->>Background: Web search results
    Background->>LLM: Derive attributes (all evidence)
    LLM-->>Background: Derived attributes
    Background->>JSON: Update with enriched data
```



## API Request Flow Diagram

```mermaid
sequenceDiagram
    participant Frontend
    participant NextJS as Next.js API Route
    participant FastAPI as FastAPI Backend
    participant GooglePlaces as Google Places API
    participant TavilyAPI as Tavily API
    participant OpenAI as OpenAI LLM

    Note over Frontend,OpenAI: Initial Search Flow
    Frontend->>NextJS: GET /api/places?bounds={...}
    NextJS->>FastAPI: POST /api/places/nearby-search
    FastAPI->>GooglePlaces: POST places:searchNearby
    GooglePlaces-->>FastAPI: nearby_results[]
    FastAPI->>FastAPI: Save basic info to JSON
    FastAPI-->>NextJS: Return basic info immediately
    NextJS-->>Frontend: Return basic info
    
    Note over Frontend,OpenAI: Background Enrichment (Top-5)
    FastAPI->>FastAPI: Background: Score & select top-5
    par Parallel API Calls
        FastAPI->>GooglePlaces: GET /places/{place_id} (reviews + binary attrs)
        FastAPI->>TavilyAPI: POST /search (web search)
    end
    GooglePlaces-->>FastAPI: Reviews + binary attributes
    TavilyAPI-->>FastAPI: Web search results
    FastAPI->>OpenAI: POST /chat/completions (derive attributes)
    OpenAI-->>FastAPI: Derived attributes
    FastAPI->>FastAPI: Update JSON with enriched data
    
    Note over Frontend,OpenAI: Ad-hoc Enrichment (User Triggered)
    Frontend->>NextJS: POST /api/places/enrich/{place_id}
    NextJS->>FastAPI: POST /api/places/enrich/{place_id}
    par Parallel API Calls
        FastAPI->>GooglePlaces: GET /places/{place_id} (reviews + binary attrs)
        FastAPI->>TavilyAPI: POST /search (web search)
    end
    GooglePlaces-->>FastAPI: Reviews + binary attributes
    TavilyAPI-->>FastAPI: Web search results
    FastAPI->>OpenAI: POST /chat/completions (derive attributes)
    OpenAI-->>FastAPI: Derived attributes
    FastAPI-->>NextJS: Return enriched place data
    NextJS-->>Frontend: Return enriched place data
```



## Key Changes Summary

1. **Immediate Response**: Return basic info from nearby_search without waiting for enrichment (name, photos, rating, types, open hours, etc. - NO binary attributes yet)
2. **Selective Enrichment**: Only enrich top-5 places based on scoring (async background task)
3. **Avoid Duplication**: When enriching, reuse basic info from nearby_search, only fetch reviews + binary attributes from place_details
4. **Parallel Async Enrichment**: place_details (reviews + binary attrs) and Tavily run in parallel, both complete before LLM runs
5. **Partial Evidence Handling**: If one API fails but the other succeeds, LLM still runs with available evidence and flags are set appropriately
6. **Ad-hoc Enrichment**: Allow users to manually enrich specific places (runs immediately, not async)
7. **New Flag**: `nearby_search_flag` to track basic info availability

## Files to Modify

1. `backend/enrichment/places_manager.py` - Add basic info extraction/saving, top-n selection