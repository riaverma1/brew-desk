-- 003_create_triggers.sql
-- AFTER INSERT ON mentions trigger: recomputes wfh_score, mention_count,
-- source_count on the parent places row. Boolean attrs are NOT set here —
-- they are majority-vote aggregations run by db_writer after a full crawl.

CREATE OR REPLACE FUNCTION recompute_place_scores()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_avg_wifi        DOUBLE PRECISION;
    v_avg_outlet      DOUBLE PRECISION;
    v_avg_noise       DOUBLE PRECISION;
    v_avg_laptop      DOUBLE PRECISION;
    v_mention_count   INTEGER;
    v_source_count    INTEGER;
    v_curated_boost   DOUBLE PRECISION;
    v_wfh_score       DOUBLE PRECISION;
BEGIN
    -- Aggregate confidence scores and counts for this place
    SELECT
        COALESCE(AVG(m.wifi_confidence),   0),
        COALESCE(AVG(m.outlet_confidence), 0),
        COALESCE(AVG(m.noise_confidence),  0),
        COALESCE(AVG(m.laptop_confidence), 0),
        COUNT(*),
        COUNT(DISTINCT m.source_id)
    INTO
        v_avg_wifi, v_avg_outlet, v_avg_noise, v_avg_laptop,
        v_mention_count, v_source_count
    FROM mentions m
    WHERE m.place_id = NEW.place_id;

    -- Curated boost: +0.5 per curated source, capped at +2.0
    SELECT LEAST(
        COALESCE(SUM(CASE WHEN s.is_curated THEN 0.5 ELSE 0 END), 0),
        2.0
    )
    INTO v_curated_boost
    FROM mentions m
    JOIN sources s ON s.id = m.source_id
    WHERE m.place_id = NEW.place_id;

    -- Score formula (0–10 scale, coefficients sum to 10.0):
    --   wfh_score = (avg_wifi_confidence   × 2.5)
    --             + (avg_outlet_confidence × 2.0)
    --             + (avg_noise_confidence  × 2.0)
    --             + (avg_laptop_confidence × 3.5)
    --             + curated_boost (capped at +2.0)
    v_wfh_score := (v_avg_wifi   * 2.5)
                 + (v_avg_outlet * 2.0)
                 + (v_avg_noise  * 2.0)
                 + (v_avg_laptop * 3.5)
                 + v_curated_boost;

    -- Store as 1-decimal float matching UI badge format ("8.4")
    v_wfh_score := ROUND(v_wfh_score::numeric, 1);

    -- Update the parent places row (trigger owns these columns)
    UPDATE places
    SET
        wfh_score     = v_wfh_score,
        mention_count = v_mention_count,
        source_count  = v_source_count
    WHERE place_id = NEW.place_id;

    RETURN NEW;
END;
$$;

-- Fire FOR EACH ROW on insert. If batch-insert performance degrades in a
-- future phase, switch to FOR EACH STATEMENT with a staging table approach.
CREATE TRIGGER trg_recompute_place_scores
AFTER INSERT ON mentions
FOR EACH ROW
EXECUTE FUNCTION recompute_place_scores();
