-- 001_create_tables.sql
-- Creates all four normalized tables with constraints and foreign keys.

-- Custom enum types
CREATE TYPE region_status AS ENUM ('cold', 'crawling', 'seeded');
CREATE TYPE noise_level AS ENUM ('quiet', 'moderate', 'loud');
CREATE TYPE platform_type AS ENUM ('reddit', 'instagram', 'blog', 'tiktok', 'google_review');
CREATE TYPE extraction_method AS ENUM ('llm', 'manual', 'heuristic');

-- regions: NYC borough/neighborhood bounding boxes
CREATE TABLE regions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_slug     TEXT NOT NULL UNIQUE,
    status        region_status NOT NULL DEFAULT 'cold',
    min_lat       DOUBLE PRECISION NOT NULL,
    max_lat       DOUBLE PRECISION NOT NULL,
    min_lng       DOUBLE PRECISION NOT NULL,
    max_lng       DOUBLE PRECISION NOT NULL,
    last_crawled_at TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- sources: content sources (subreddits, Instagram accounts, blogs, etc.)
CREATE TABLE sources (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    platform          platform_type NOT NULL,
    handle_or_domain  TEXT NOT NULL,
    is_curated        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (platform, handle_or_domain)
);

-- places: canonical enriched coffee shops
CREATE TABLE places (
    place_id          TEXT PRIMARY KEY,           -- Google Maps place_id
    name              TEXT NOT NULL,
    address           TEXT,
    lat               DOUBLE PRECISION NOT NULL,
    lng               DOUBLE PRECISION NOT NULL,
    region_id         UUID REFERENCES regions(id),

    -- WFH attributes (majority-vote aggregations set by db_writer after crawl)
    has_wifi          BOOLEAN,
    has_outlets       BOOLEAN,
    is_laptop_friendly BOOLEAN,
    noise_level       noise_level,
    seating_comfort   TEXT,

    -- Trigger-owned aggregate fields (do NOT write directly)
    wfh_score         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    mention_count     INTEGER NOT NULL DEFAULT 0,
    source_count      INTEGER NOT NULL DEFAULT 0,

    -- Google Places metadata (written by routers/places.py on each nearby search)
    photos            JSONB DEFAULT '[]'::jsonb,  -- array of photo media URLs
    primary_type      TEXT,                        -- e.g. "cafe", "bakery", "library"
    rating            DOUBLE PRECISION,            -- Google star rating (1.0–5.0)
    user_rating_count INTEGER,                     -- number of Google reviews
    regular_opening_hours JSONB,                   -- {weekdayDescriptions: [...], openNow: bool}

    last_enriched_at  TIMESTAMPTZ,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- mentions: individual web mentions linking a source to a place (or unmatched)
-- place_id is nullable: crawler saves mentions with place_id=NULL when no place
-- could be resolved. These "unmatched" mentions are cached so they can be paired
-- with a place_id later when new regions are seeded, without re-scraping.
CREATE TABLE mentions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    place_id            TEXT REFERENCES places(place_id) ON DELETE CASCADE,  -- NULL = unmatched
    source_id           UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,

    url                 TEXT NOT NULL UNIQUE,       -- primary dedup key (deduplicates across crawl runs)
    evidence_snippet    TEXT,                       -- direct quote from raw text shown in UI
    method              extraction_method NOT NULL DEFAULT 'llm',

    -- Per-mention confidence scores (0.0–1.0)
    wifi_confidence     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    outlet_confidence   DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    noise_confidence    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    laptop_confidence   DOUBLE PRECISION NOT NULL DEFAULT 0.0,

    mentioned_at        TIMESTAMPTZ,               -- publication date if known
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
