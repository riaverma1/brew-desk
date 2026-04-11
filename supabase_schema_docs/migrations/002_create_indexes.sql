-- 002_create_indexes.sql
-- Performance indexes for the map pan hot path and crawler write path.

-- Hot path: bounding box filter for pin queries
CREATE INDEX idx_places_lat_lng ON places(lat, lng);

-- Hot path: partial index for pin-eligible places only (biggest single latency win)
CREATE INDEX idx_places_score_filtered ON places(place_id, wfh_score)
    WHERE wfh_score >= 6.0;

-- Click flow: mentions ordered by confidence for InfoCard
CREATE INDEX idx_mentions_place_laptop ON mentions(place_id, laptop_confidence DESC);

-- Crawler dedup: fast URL collision check
CREATE UNIQUE INDEX idx_mentions_url ON mentions(url);

-- Region bounding box lookup for viewport detection
CREATE INDEX idx_regions_bbox ON regions(min_lat, max_lat, min_lng, max_lng);

-- Source dedup: prevent duplicate source rows from concurrent crawlers
CREATE UNIQUE INDEX idx_sources_platform_handle ON sources(platform, handle_or_domain);

-- Crawler: place lookup by region for post-crawl boolean attr recompute
CREATE INDEX idx_places_region_id ON places(region_id);
