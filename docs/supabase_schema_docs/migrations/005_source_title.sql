-- Add source_title to mentions table.
-- Stores the article/thread title captured at crawl time.
-- Nullable: existing rows and failed fetches remain NULL and fall back to domain-only display.
ALTER TABLE mentions ADD COLUMN IF NOT EXISTS source_title TEXT;
