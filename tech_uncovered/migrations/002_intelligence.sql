ALTER TABLE research_runs ADD COLUMN created_at TEXT;
CREATE TABLE intelligence_runs (
 intelligence_run_id TEXT PRIMARY KEY, radar_run_id TEXT NOT NULL,
 created_at TEXT NOT NULL, source_observed_at TEXT NOT NULL,
 mode TEXT NOT NULL, status TEXT NOT NULL, expired INTEGER NOT NULL DEFAULT 0,
 payload TEXT NOT NULL
);
CREATE TABLE intelligence_candidates (
 intelligence_run_id TEXT NOT NULL REFERENCES intelligence_runs ON DELETE CASCADE,
 source_video_id TEXT NOT NULL, radar_run_id TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY (intelligence_run_id, source_video_id)
);
CREATE TABLE transcripts (
 intelligence_run_id TEXT NOT NULL REFERENCES intelligence_runs ON DELETE CASCADE,
 source_video_id TEXT NOT NULL, transcript_status TEXT NOT NULL,
 provider_name TEXT NOT NULL, provider_version TEXT NOT NULL, content_hash TEXT NOT NULL,
 retrieved_at TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, source_video_id)
);
CREATE TABLE evidence_sources (
 intelligence_run_id TEXT NOT NULL REFERENCES intelligence_runs ON DELETE CASCADE,
 source_video_id TEXT NOT NULL, evidence_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, source_video_id, evidence_id)
);
CREATE TABLE story_briefs (
 intelligence_run_id TEXT NOT NULL REFERENCES intelligence_runs ON DELETE CASCADE,
 source_video_id TEXT NOT NULL, radar_run_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, source_video_id)
);
CREATE TABLE trend_clusters (
 intelligence_run_id TEXT NOT NULL REFERENCES intelligence_runs ON DELETE CASCADE,
 cluster_id TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, cluster_id)
);
CREATE TABLE trend_cluster_videos (
 intelligence_run_id TEXT NOT NULL, cluster_id TEXT NOT NULL, source_video_id TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, cluster_id, source_video_id),
 FOREIGN KEY (intelligence_run_id, cluster_id) REFERENCES trend_clusters ON DELETE CASCADE
);
CREATE TABLE idea_candidates (
 intelligence_run_id TEXT NOT NULL REFERENCES intelligence_runs ON DELETE CASCADE,
 idea_id TEXT NOT NULL, production_ready INTEGER NOT NULL, similarity_status TEXT NOT NULL,
 category TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, idea_id)
);
CREATE TABLE idea_sources (
 intelligence_run_id TEXT NOT NULL, idea_id TEXT NOT NULL, source_video_id TEXT NOT NULL,
 PRIMARY KEY (intelligence_run_id, idea_id, source_video_id),
 FOREIGN KEY (intelligence_run_id, idea_id) REFERENCES idea_candidates ON DELETE CASCADE
);
CREATE TABLE idea_scores (
 intelligence_run_id TEXT NOT NULL, idea_id TEXT NOT NULL, scoring_version TEXT NOT NULL,
 demand_signal REAL NOT NULL, freshness REAL NOT NULL, originality REAL NOT NULL,
 audience_fit REAL NOT NULL, production_fit REAL NOT NULL, evidence_quality REAL NOT NULL,
 expandability REAL NOT NULL, saturation_risk REAL NOT NULL, idea_score REAL NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY (intelligence_run_id, idea_id),
 FOREIGN KEY (intelligence_run_id, idea_id) REFERENCES idea_candidates ON DELETE CASCADE
);
CREATE INDEX intelligence_radar_run ON intelligence_runs(radar_run_id);
