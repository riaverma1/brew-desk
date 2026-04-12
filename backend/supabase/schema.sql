-- schema.sql
-- Full DDL for the coffee_app database.
-- Run this on a clean Supabase project (or after dropping all tables/types).
-- Apply in Supabase Dashboard → SQL Editor, or via psql.

-- ============================================================
-- CLEANUP (safe to re-run on a fresh DB)
-- ============================================================
DROP TABLE IF EXISTS mentions CASCADE;
DROP TABLE IF EXISTS places   CASCADE;
DROP TABLE IF EXISTS sources  CASCADE;
DROP TABLE IF EXISTS regions  CASCADE;

DROP TYPE IF EXISTS region_status     CASCADE;
DROP TYPE IF EXISTS noise_level       CASCADE;
DROP TYPE IF EXISTS platform_type     CASCADE;
DROP TYPE IF EXISTS extraction_method CASCADE;

DROP FUNCTION IF EXISTS recompute_place_scores() CASCADE;

-- ============================================================
-- CUSTOM TYPES
-- ============================================================
CREATE TYPE region_status     AS ENUM ('cold', 'crawling', 'seeded');
CREATE TYPE noise_level       AS ENUM ('quiet', 'moderate', 'loud');
CREATE TYPE platform_type     AS ENUM ('reddit', 'instagram', 'blog', 'tiktok', 'google_review');
CREATE TYPE extraction_method AS ENUM ('llm', 'manual', 'heuristic');

-- ============================================================
-- TABLE: regions
-- NYC borough / neighborhood bounding boxes.
-- ============================================================
CREATE TABLE regions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  city_slug       TEXT NOT NULL UNIQUE,
  status          region_status NOT NULL DEFAULT 'cold',
  min_lat         DOUBLE PRECISION NOT NULL,
  max_lat         DOUBLE PRECISION NOT NULL,
  min_lng         DOUBLE PRECISION NOT NULL,
  max_lng         DOUBLE PRECISION NOT NULL,
  last_crawled_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- TABLE: sources
-- Content origins — subreddits, Instagram accounts, blogs, etc.
-- ============================================================
CREATE TABLE sources (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  platform         platform_type NOT NULL,
  handle_or_domain TEXT NOT NULL,
  is_curated       BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (platform, handle_or_domain)
);

-- ============================================================
-- TABLE: mentions
-- Created BEFORE places. place_id is nullable and has NO FK —
-- mentions are the source of truth, places are derived.
--
-- Pipeline:
--   Step 1 (crawl):   saved with place_id = NULL
--   Step 2 (resolve): place_id updated to Google place_id
-- ============================================================
CREATE TABLE mentions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  place_name_raw    TEXT NOT NULL,              -- name as written in the source article
  place_id          TEXT,                       -- NULL until resolver runs; intentionally no FK

  source_id         UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  url               TEXT NOT NULL,
  evidence_snippet  TEXT,                       -- verbatim quote shown in the UI

  method            extraction_method NOT NULL DEFAULT 'llm',

  -- Per-mention WFH confidence scores (0.0–1.0)
  wifi_confidence    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  outlet_confidence  DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  -- quiet_confidence: HIGH = quiet = good for WFH (replaces old noise_confidence)
  quiet_confidence   DOUBLE PRECISION NOT NULL DEFAULT 0.5,
  laptop_confidence  DOUBLE PRECISION NOT NULL DEFAULT 0.0,

  mentioned_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Dedup: same article can mention multiple places; same article can't mention
  -- the same place twice.
  UNIQUE (url, place_name_raw)
);

-- ============================================================
-- TABLE: places
-- Created/enriched during the nearby search hot path.
-- Minimal rows are also created by resolver_job when place_id is assigned.
-- Google metadata (photos, hours, rating) is written during nearby search.
-- ============================================================
CREATE TABLE places (
  place_id          TEXT PRIMARY KEY,           -- Google Maps place_id

  name              TEXT NOT NULL,
  address           TEXT,
  lat               DOUBLE PRECISION NOT NULL,
  lng               DOUBLE PRECISION NOT NULL,
  region_id         UUID REFERENCES regions(id),

  -- WFH boolean attributes
  -- Set by resolver_job via majority-vote after resolution completes.
  has_wifi           BOOLEAN,
  has_outlets        BOOLEAN,
  is_laptop_friendly BOOLEAN,
  noise_level        noise_level,
  seating_comfort    TEXT,

  -- Trigger-owned aggregate fields — DO NOT write directly from Python.
  -- Updated automatically by recompute_place_scores() on mention INSERT/UPDATE.
  wfh_score         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
  mention_count     INTEGER NOT NULL DEFAULT 0,
  source_count      INTEGER NOT NULL DEFAULT 0,

  -- Google Places metadata — written by routers/places.py on each nearby search.
  photos                JSONB DEFAULT '[]'::jsonb,
  primary_type          TEXT,
  rating                DOUBLE PRECISION,
  user_rating_count     INTEGER,
  regular_opening_hours JSONB,

  last_enriched_at  TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- TRIGGER: recompute_place_scores
-- Fires AFTER INSERT OR UPDATE on mentions when place_id IS NOT NULL.
-- Recomputes wfh_score, mention_count, source_count on the parent places row.
--
-- NOTE: Boolean attrs (has_wifi, has_outlets, is_laptop_friendly, noise_level)
-- are NOT set here — they use majority-vote logic run by resolver_job after
-- all mentions for a region are resolved.
--
-- Score formula (0–10 scale, coefficients sum to 10.0):
--   wfh_score = (avg_wifi    × 2.5)
--             + (avg_outlet  × 2.0)
--             + (avg_quiet   × 2.0)   ← quiet = good (high = quiet)
--             + (avg_laptop  × 3.5)
--             + curated_boost (capped at +2.0)
-- ============================================================
CREATE OR REPLACE FUNCTION recompute_place_scores()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
  v_avg_wifi      DOUBLE PRECISION;
  v_avg_outlet    DOUBLE PRECISION;
  v_avg_quiet     DOUBLE PRECISION;
  v_avg_laptop    DOUBLE PRECISION;
  v_mention_count INTEGER;
  v_source_count  INTEGER;
  v_curated_boost DOUBLE PRECISION;
  v_wfh_score     DOUBLE PRECISION;
BEGIN
  -- Only recompute when place_id is set
  IF NEW.place_id IS NULL THEN
      RETURN NEW;
  END IF;

  -- Aggregate confidence scores for all resolved mentions of this place
  SELECT
      COALESCE(AVG(m.wifi_confidence),    0),
      COALESCE(AVG(m.outlet_confidence),  0),
      COALESCE(AVG(m.quiet_confidence),   0),
      COALESCE(AVG(m.laptop_confidence),  0),
      COUNT(*),
      COUNT(DISTINCT m.source_id)
  INTO
      v_avg_wifi, v_avg_outlet, v_avg_quiet, v_avg_laptop,
      v_mention_count, v_source_count
  FROM mentions m
  WHERE m.place_id = NEW.place_id;

  -- Curated boost: +0.5 per curated source mention, capped at +2.0
  SELECT LEAST(
      COALESCE(SUM(CASE WHEN s.is_curated THEN 0.5 ELSE 0 END), 0),
      2.0
  )
  INTO v_curated_boost
  FROM mentions m
  JOIN sources s ON s.id = m.source_id
  WHERE m.place_id = NEW.place_id;

  v_wfh_score := (v_avg_wifi   * 2.5)
                + (v_avg_outlet * 2.0)
                + (v_avg_quiet  * 2.0)
                + (v_avg_laptop * 3.5)
                + v_curated_boost;

  -- Cap at 10.0 and round to 1 decimal (matches UI badge format "8.4")
  v_wfh_score := ROUND(LEAST(v_wfh_score, 10.0)::numeric, 1);

  UPDATE places
  SET
      wfh_score     = v_wfh_score,
      mention_count = v_mention_count,
      source_count  = v_source_count
  WHERE place_id = NEW.place_id;

  RETURN NEW;
END;
$$;

-- Fires on INSERT (new mention) and UPDATE (when place_id is assigned by resolver)
CREATE TRIGGER trg_recompute_place_scores
AFTER INSERT OR UPDATE ON mentions
FOR EACH ROW
EXECUTE FUNCTION recompute_place_scores();

-- ============================================================
-- INDEXES
-- ============================================================

-- Map pan hot path: bounding box filter on lat/lng
DROP INDEX IF EXISTS idx_places_lat_lng;
CREATE INDEX idx_places_lat_lng ON places(lat, lng);

-- InfoCard: mentions ordered by laptop_confidence for a place
DROP INDEX IF EXISTS idx_mentions_place_laptop;
CREATE INDEX idx_mentions_place_laptop ON mentions(place_id, laptop_confidence DESC)
  WHERE place_id IS NOT NULL;

-- Resolver job: find all unresolved mentions efficiently
DROP INDEX IF EXISTS idx_mentions_unresolved;
CREATE INDEX idx_mentions_unresolved   ON mentions(place_id)
  WHERE place_id IS NULL;

-- Region viewport detection
DROP INDEX IF EXISTS idx_regions_bbox;
CREATE INDEX idx_regions_bbox          ON regions(min_lat, max_lat, min_lng, max_lng);

-- Boolean attr recompute: all places in a region
DROP INDEX IF EXISTS idx_places_region;
CREATE INDEX idx_places_region         ON places(region_id);

-- Unique dedup indexes (enforce the UNIQUE constraints with explicit names)
DROP INDEX IF EXISTS idx_sources_dedup;
DROP INDEX IF EXISTS idx_mentions_dedup;
CREATE UNIQUE INDEX idx_sources_dedup  ON sources(platform, handle_or_domain);
CREATE UNIQUE INDEX idx_mentions_dedup ON mentions(url, place_name_raw);
