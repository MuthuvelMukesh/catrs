CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS traffic_readings (
    segment_id TEXT NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    avg_speed DOUBLE PRECISION NOT NULL CHECK (avg_speed >= 0),
    vehicle_count INTEGER NOT NULL CHECK (vehicle_count >= 0),
    PRIMARY KEY (segment_id, observed_at)
);

SELECT create_hypertable('traffic_readings', 'observed_at', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS historical_baselines (
    segment_id TEXT NOT NULL,
    weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    hour SMALLINT NOT NULL CHECK (hour BETWEEN 0 AND 23),
    avg_speed DOUBLE PRECISION NOT NULL CHECK (avg_speed >= 0),
    sample_count INTEGER NOT NULL CHECK (sample_count > 0),
    PRIMARY KEY (segment_id, weekday, hour)
);

CREATE TABLE IF NOT EXISTS weight_schedules (
    version TEXT PRIMARY KEY,
    effective_date DATE NOT NULL UNIQUE,
    weights JSONB NOT NULL CHECK (jsonb_typeof(weights) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS route_outcomes (
    route_id TEXT NOT NULL,
    trip_category TEXT NOT NULL,
    weight_schedule_version TEXT NOT NULL REFERENCES weight_schedules(version),
    weight_applied DOUBLE PRECISION NOT NULL,
    predicted_travel_time_s DOUBLE PRECISION NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (route_id, observed_at)
);

CREATE TABLE IF NOT EXISTS audit_results (
    id BIGSERIAL PRIMARY KEY,
    route_id TEXT NOT NULL,
    outcome_at TIMESTAMPTZ NOT NULL,
    weight_schedule_version TEXT NOT NULL,
    valid BOOLEAN NOT NULL,
    failures JSONB NOT NULL DEFAULT '[]'::jsonb,
    audited_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
