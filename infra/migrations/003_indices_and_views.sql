-- 003: Performance indices and reporting views for routing and audit analysis.

-- Indices on route outcomes for audit queries and compliance verification
CREATE INDEX IF NOT EXISTS idx_route_outcomes_trip_version
    ON route_outcomes (trip_category, weight_schedule_version);

CREATE INDEX IF NOT EXISTS idx_route_outcomes_observed_time
    ON route_outcomes (observed_at DESC);

-- Indices on audit results for filtering invalid decisions and fast retrieval
CREATE INDEX IF NOT EXISTS idx_audit_results_valid_time
    ON audit_results (valid, audited_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_results_route_lookup
    ON audit_results (route_id, outcome_at DESC);

-- Index on weight schedules for effective date range lookups
CREATE INDEX IF NOT EXISTS idx_weight_schedules_effective_desc
    ON weight_schedules (effective_date DESC);

-- View: Policy compliance summary by weight schedule version
CREATE OR REPLACE VIEW v_policy_compliance_summary AS
SELECT
    weight_schedule_version,
    COUNT(*) AS total_audits,
    COUNT(*) FILTER (WHERE valid = TRUE) AS valid_count,
    COUNT(*) FILTER (WHERE valid = FALSE) AS invalid_count,
    ROUND((COUNT(*) FILTER (WHERE valid = TRUE)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS compliance_rate_pct,
    MIN(outcome_at) AS earliest_outcome,
    MAX(outcome_at) AS latest_outcome
FROM audit_results
GROUP BY weight_schedule_version;

-- View: Hourly segment congestion profile
CREATE OR REPLACE VIEW v_segment_congestion_hourly AS
SELECT
    segment_id,
    EXTRACT(DOW FROM observed_at)::smallint AS weekday,
    EXTRACT(HOUR FROM observed_at)::smallint AS hour,
    ROUND(AVG(avg_speed)::NUMERIC, 2) AS avg_speed_kmh,
    ROUND(AVG(vehicle_count)::NUMERIC, 0) AS avg_vehicle_count,
    COUNT(*) AS sample_count
FROM traffic_readings
GROUP BY segment_id, weekday, hour;
