CREATE TABLE radar_market_runs (
 run_id TEXT PRIMARY KEY REFERENCES research_runs(run_id),
 competitor_config_version TEXT NOT NULL, cohort_config_version TEXT NOT NULL,
 scoring_version TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE radar_opportunities (
 run_id TEXT NOT NULL REFERENCES radar_market_runs(run_id), video_id TEXT NOT NULL,
 market_cohort TEXT NOT NULL, source_role TEXT NOT NULL, researchability_score REAL NOT NULL,
 normalized_radar_signal REAL, cross_cohort_support REAL NOT NULL, opportunity_score REAL,
 payload TEXT NOT NULL, PRIMARY KEY(run_id,video_id)
);
CREATE TABLE radar_cohort_summaries (
 run_id TEXT NOT NULL REFERENCES radar_market_runs(run_id), market_cohort TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(run_id,market_cohort)
);
CREATE TABLE radar_cross_cohort_signals (
 run_id TEXT NOT NULL REFERENCES radar_market_runs(run_id), canonical_topic TEXT NOT NULL,
 independent_channel_count INTEGER NOT NULL, vendor_channel_count INTEGER NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(run_id,canonical_topic)
);
