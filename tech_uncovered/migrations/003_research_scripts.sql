CREATE TABLE research_runs_v3 (
 research_run_id TEXT PRIMARY KEY, script_run_id TEXT NOT NULL UNIQUE,
 radar_run_id TEXT NOT NULL, intelligence_run_id TEXT NOT NULL, idea_id TEXT NOT NULL,
 provider_version TEXT NOT NULL, generation_version TEXT NOT NULL, configuration_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, source_observed_at TEXT NOT NULL, mode TEXT NOT NULL,
 selected_snapshot TEXT NOT NULL, plan TEXT NOT NULL, outcome TEXT NOT NULL
);
CREATE TABLE research_sources (research_run_id TEXT NOT NULL REFERENCES research_runs_v3, source_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(research_run_id,source_id));
CREATE TABLE research_claims (research_run_id TEXT NOT NULL REFERENCES research_runs_v3, claim_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(research_run_id,claim_id));
CREATE TABLE research_claim_evidence (research_run_id TEXT NOT NULL REFERENCES research_runs_v3, claim_id TEXT NOT NULL, passage_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(research_run_id,claim_id,passage_id));
CREATE TABLE research_packets (research_packet_id TEXT PRIMARY KEY, research_run_id TEXT NOT NULL UNIQUE REFERENCES research_runs_v3, payload TEXT NOT NULL);
CREATE TABLE script_runs (script_run_id TEXT PRIMARY KEY, research_run_id TEXT NOT NULL REFERENCES research_runs_v3, status TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE script_drafts (script_run_id TEXT NOT NULL REFERENCES script_runs, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(script_run_id,revision));
CREATE TABLE script_hooks (script_run_id TEXT NOT NULL, revision INTEGER NOT NULL, hook_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(script_run_id,revision,hook_id), FOREIGN KEY(script_run_id,revision) REFERENCES script_drafts);
CREATE TABLE script_claim_map (script_run_id TEXT NOT NULL, revision INTEGER NOT NULL, sentence_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(script_run_id,revision,sentence_id), FOREIGN KEY(script_run_id,revision) REFERENCES script_drafts);
CREATE TABLE script_fact_checks (script_run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(script_run_id,revision), FOREIGN KEY(script_run_id,revision) REFERENCES script_drafts);
CREATE TABLE script_quality_reviews (script_run_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(script_run_id,revision), FOREIGN KEY(script_run_id,revision) REFERENCES script_drafts);
CREATE TABLE script_cost_records (script_run_id TEXT PRIMARY KEY REFERENCES script_runs, payload TEXT NOT NULL);
CREATE TRIGGER immutable_script_draft BEFORE UPDATE ON script_drafts BEGIN SELECT RAISE(ABORT,'Script revisions are append-only'); END;
