-- 002: Materialized view and function for baseline refresh from traffic_readings.
-- This supplements the application-level refresh_from_readings() query with
-- a server-side function for scheduled maintenance.

CREATE OR REPLACE FUNCTION refresh_historical_baselines()
RETURNS INTEGER AS $$
DECLARE
    affected INTEGER;
BEGIN
    INSERT INTO historical_baselines (segment_id, weekday, hour, avg_speed, sample_count)
    SELECT
        segment_id,
        EXTRACT(DOW FROM observed_at)::smallint AS weekday,
        EXTRACT(HOUR FROM observed_at)::smallint AS hour,
        AVG(avg_speed) AS avg_speed,
        COUNT(*)::integer AS sample_count
    FROM traffic_readings
    GROUP BY segment_id, weekday, hour
    ON CONFLICT (segment_id, weekday, hour) DO UPDATE SET
        avg_speed = EXCLUDED.avg_speed,
        sample_count = EXCLUDED.sample_count;

    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- Index for common query pattern: recent readings by segment
CREATE INDEX IF NOT EXISTS idx_traffic_readings_segment_time
    ON traffic_readings (segment_id, observed_at DESC);

-- Index for baseline lookups
CREATE INDEX IF NOT EXISTS idx_historical_baselines_lookup
    ON historical_baselines (segment_id, weekday, hour);
