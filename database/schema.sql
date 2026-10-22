CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS policies (
    policy_id SERIAL PRIMARY KEY,
    policy_name TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE,
    crime_type TEXT,
    geographic_scope TEXT,
    description TEXT
);

CREATE TABLE IF NOT EXISTS crime_features (
    feature_id BIGSERIAL PRIMARY KEY,
    cuadrante TEXT NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    crime_count INTEGER NOT NULL DEFAULT 0,
    lag_1 INTEGER,
    lag_3 INTEGER,
    rolling_3_month DOUBLE PRECISION,
    neighbor_crime_count INTEGER,
    policy_active INTEGER NOT NULL DEFAULT 0,
    target_next_month INTEGER
);
