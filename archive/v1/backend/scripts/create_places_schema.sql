-- Create places table for Supabase Postgres
-- Run this in your Supabase SQL editor

CREATE TABLE IF NOT EXISTS places (
    place_id TEXT PRIMARY KEY,
    nearby_search_flag BOOLEAN DEFAULT FALSE,
    places_details_flag BOOLEAN DEFAULT FALSE,
    tavily_flag BOOLEAN DEFAULT FALSE,
    enriched_flag BOOLEAN DEFAULT FALSE,
    place JSONB DEFAULT '{}'::jsonb,
    sources JSONB DEFAULT '{}'::jsonb,
    derived JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_places_enriched_flag ON places(enriched_flag) WHERE enriched_flag = FALSE;
CREATE INDEX IF NOT EXISTS idx_places_place_gin ON places USING GIN(place);
CREATE INDEX IF NOT EXISTS idx_places_updated_at ON places(updated_at);

-- Create function to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger to update updated_at on row updates
CREATE TRIGGER update_places_updated_at
    BEFORE UPDATE ON places
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

