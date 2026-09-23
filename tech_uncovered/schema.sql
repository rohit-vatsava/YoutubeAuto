-- Bootstrap version 1 only; Database applies ordered migrations after creation.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS channels (
 channel_id TEXT PRIMARY KEY, name TEXT NOT NULL, handle TEXT, uploads_playlist_id TEXT,
 observed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
 video_id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, channel TEXT NOT NULL,
 title TEXT NOT NULL, published_at TEXT NOT NULL, views INTEGER, likes INTEGER,
 comments INTEGER, duration_seconds INTEGER, url TEXT NOT NULL, observed_at TEXT NOT NULL,
 available INTEGER NOT NULL, is_live INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS api_cache (
 cache_key TEXT PRIMARY KEY, payload TEXT NOT NULL, observed_at TEXT NOT NULL,
 expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_runs (
 run_id TEXT PRIMARY KEY, observed_at TEXT NOT NULL, payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS baselines (
 run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
 channel_id TEXT NOT NULL, cohort TEXT NOT NULL, sample_size INTEGER NOT NULL,
 median_views REAL, median_views_per_day REAL, small_sample INTEGER NOT NULL,
 PRIMARY KEY (run_id, channel_id, cohort)
);
CREATE TABLE IF NOT EXISTS video_scores (
 run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
 video_id TEXT NOT NULL, cohort TEXT, outlier_ratio REAL, velocity_ratio REAL,
 velocity_adjusted_score REAL, percentile REAL, baseline_sample_size INTEGER NOT NULL,
 baseline_median_views REAL, baseline_median_views_per_day REAL,
 eligibility_reason TEXT NOT NULL, provisional INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (run_id, video_id)
);
CREATE TABLE IF NOT EXISTS topic_groups (
 run_id TEXT NOT NULL REFERENCES research_runs(run_id) ON DELETE CASCADE,
 theme TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY (run_id, theme)
);
PRAGMA user_version = 1;
