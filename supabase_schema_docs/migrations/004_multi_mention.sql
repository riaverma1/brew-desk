-- 004_multi_mention.sql
-- Relaxes the UNIQUE(url) constraint on mentions to allow multiple rows per URL
-- (one per distinct place mentioned). Adds place_name_raw as the secondary dedup
-- key and is_multi_processed to track which rows have been through the retroactive
-- multi-mention extractor.
--
-- Dedup semantics after this migration:
--   Original crawl row (single-match or unmatched): (url, '', is_multi_processed=FALSE)
--   After retroactive job runs on that URL:         (url, '', is_multi_processed=TRUE)
--   New multi-mention output rows:                  (url, 'cafe grumpy', ...)
--
-- Deploy order: run this migration BEFORE deploying updated backend code
-- (db_writer uses on_conflict="url,place_name_raw" which requires this constraint).

-- 1. Add place_name_raw — empty string default so all existing rows satisfy
--    the new composite unique constraint as (url, '') without a data migration.
ALTER TABLE mentions
    ADD COLUMN place_name_raw TEXT NOT NULL DEFAULT '';

-- 2. Add is_multi_processed — FALSE for all existing rows (not yet processed).
ALTER TABLE mentions
    ADD COLUMN is_multi_processed BOOLEAN NOT NULL DEFAULT FALSE;

-- 3. Drop the old unique constraints and their indexes.
--    mentions_url_key: old UNIQUE(url) — replaced by composite below
--    mentions_place_id_url_key: old UNIQUE(place_id, url) — obsolete now that
--    multiple rows per (place_id, url) are allowed (different place_name_raw)
ALTER TABLE mentions DROP CONSTRAINT IF EXISTS mentions_url_key;
ALTER TABLE mentions DROP CONSTRAINT IF EXISTS mentions_place_id_url_key;
DROP INDEX IF EXISTS idx_mentions_url;

-- 4. New composite unique constraint: (url, place_name_raw).
--    Supabase upserts use on_conflict="url,place_name_raw" against this constraint.
ALTER TABLE mentions
    ADD CONSTRAINT mentions_url_place_name_unique UNIQUE (url, place_name_raw);

-- 5. Recreate the supporting index under the new name.
CREATE UNIQUE INDEX idx_mentions_url_place ON mentions (url, place_name_raw);

-- 6. Index to make the retroactive matcher query fast:
--    SELECT ... WHERE place_name_raw = '' AND is_multi_processed = FALSE
CREATE INDEX idx_mentions_retroactive
    ON mentions (is_multi_processed, place_name_raw)
    WHERE place_name_raw = '' AND is_multi_processed = FALSE;
