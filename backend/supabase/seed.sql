-- seed.sql
-- Run AFTER schema.sql.

-- NYC Manhattan (original)
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('nyc-manhattan', 'cold', 40.6982, 40.8820, -74.0479, -73.9067)
ON CONFLICT (city_slug) DO NOTHING;

-- NYC Queens
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('nyc-queens', 'cold', 40.5431, 40.8007, -73.9623, -73.7004)
ON CONFLICT (city_slug) DO NOTHING;

-- NYC Brooklyn
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('nyc-brooklyn', 'cold', 40.5707, 40.7395, -74.0421, -73.8333)
ON CONFLICT (city_slug) DO NOTHING;

-- Chicago
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('chicago', 'cold', 41.6445, 42.0228, -87.9401, -87.5237)
ON CONFLICT (city_slug) DO NOTHING;

-- Phoenix
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('phoenix', 'cold', 33.2981, 33.8903, -112.3240, -111.9258)
ON CONFLICT (city_slug) DO NOTHING;

-- Albuquerque
INSERT INTO regions (city_slug, status, min_lat, max_lat, min_lng, max_lng)
VALUES ('albuquerque', 'cold', 35.0117, 35.2183, -106.8316, -106.4706)
ON CONFLICT (city_slug) DO NOTHING;
