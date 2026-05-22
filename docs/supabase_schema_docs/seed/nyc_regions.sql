-- nyc_regions.sql
-- Pre-seeds NYC borough bounding boxes with status='cold'.
--
-- Phase 1: Manhattan only. Other boroughs are commented out to prevent
-- the cold-region seed job from being triggered before Phase 2.
-- Insert as 'cold', NOT 'seeded' — the crawler flips the status.

INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('nyc-manhattan', 'cold', 40.6998, 40.8820, -74.0479, -73.9067);

-- Phase 2 (uncomment when ready to expand):
-- INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
-- VALUES
--   ('nyc-brooklyn',      'cold', 40.5700, 40.7395, -74.0419, -73.8334),
--   ('nyc-queens',        'cold', 40.5430, 40.8007, -73.9621, -73.7004),
--   ('nyc-bronx',         'cold', 40.7855, 40.9176, -73.9338, -73.7654),
--   ('nyc-staten-island', 'cold', 40.4960, 40.6490, -74.2591, -74.0522);
