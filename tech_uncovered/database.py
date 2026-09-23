import json
import sqlite3
from datetime import timedelta
from pathlib import Path

from .settings import parse_time
from .intelligence.storage import expire


class Database:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 4:
            self.connection.close()
            raise ValueError("Database schema is newer than this application")
        if version == 0:
            self.connection.executescript(Path(__file__).with_name("schema.sql").read_text())
            version = 1
        if version == 1:
            backup_path = Path(str(path) + ".pre-v2.bak")
            if not backup_path.exists():
                backup = sqlite3.connect(backup_path)
                self.connection.backup(backup)
                backup.close()
            sql = (Path(__file__).parent / "migrations/002_intelligence.sql").read_text()
            try:
                self.connection.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=2;\nCOMMIT;")
            except Exception:
                self.connection.rollback()
                self.connection.close()
                raise
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 2:
            backup_path = Path(str(path) + ".pre-v3.bak")
            if not backup_path.exists():
                backup = sqlite3.connect(backup_path)
                self.connection.backup(backup)
                backup.close()
            sql = (Path(__file__).parent / "migrations/003_research_scripts.sql").read_text()
            try:
                self.connection.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=3;\nCOMMIT;")
            except Exception:
                self.connection.rollback()
                self.connection.close()
                raise
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 3:
            backup_path = Path(str(path) + ".pre-v4.bak")
            if not backup_path.exists():
                backup = sqlite3.connect(backup_path)
                self.connection.backup(backup)
                backup.close()
            sql = (Path(__file__).parent / "migrations/004_market_radar.sql").read_text()
            try:
                self.connection.executescript("BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version=4;\nCOMMIT;")
            except Exception:
                self.connection.rollback()
                self.connection.close()
                raise
        self.connection.execute("PRAGMA foreign_keys=ON")

    def close(self):
        self.connection.close()

    def cached(self, key, now):
        row = self.connection.execute("SELECT * FROM api_cache WHERE cache_key=?", (key,)).fetchone()
        if row and parse_time(row["expires_at"]) > now:
            return json.loads(row["payload"]), row["observed_at"]
        return None

    def cache(self, key, payload, now, ttl):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO api_cache VALUES (?,?,?,?)",
                                    (key, json.dumps(payload), now.isoformat(), (now + ttl).isoformat()))

    def prune(self, now):
        cutoff = (now - timedelta(days=30)).isoformat()
        expire(self, now)
        from .scripting.storage import expire as expire_scripts
        expire_scripts(self, now)
        with self.connection:
            for table in ("api_cache",):
                self.connection.execute(f"DELETE FROM {table} WHERE observed_at <= ?", (cutoff,))

    def prune_cache(self, now):
        with self.connection:
            self.connection.execute("DELETE FROM api_cache WHERE expires_at <= ?", (now.isoformat(),))

    def save_channel(self, channel):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO channels VALUES (:channel_id,:name,:handle,:uploads_playlist_id,:observed_at)", channel)

    def save_videos(self, videos):
        with self.connection:
            self.connection.executemany("""INSERT OR REPLACE INTO videos VALUES
                (:video_id,:channel_id,:channel,:title,:published_at,:views,:likes,:comments,
                 :duration_seconds,:url,:observed_at,:available,:is_live)""", videos)

    def load_videos(self, channel_ids=None):
        rows = [dict(r) for r in self.connection.execute("SELECT * FROM videos ORDER BY video_id")]
        return [r for r in rows if channel_ids is None or r["channel_id"] in channel_ids]

    def load_channels(self):
        return [dict(r) for r in self.connection.execute("SELECT * FROM channels")]

    def save_run(self, result):
        run_id = result["run_id"]
        with self.connection:
            self.connection.execute("INSERT INTO research_runs (run_id,observed_at,payload,created_at) VALUES (?,?,?,?)",
                                    (run_id, min([result["generated_at"]] + [r["observed_at"] for r in result["videos"]]), json.dumps(result["metadata"]), result["generated_at"]))
            for baseline in result["baselines"]:
                self.connection.execute("INSERT INTO baselines VALUES (?,?,?,?,?,?,?)", (
                    run_id, baseline["channel_id"], baseline["cohort"], baseline["sample_size"],
                    baseline["median_views"], baseline["median_views_per_day"], baseline["small_sample"]))
            for row in result["videos"]:
                self.connection.execute("INSERT INTO video_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    run_id, row["video_id"], row["cohort"], row["outlier_ratio"], row["velocity_ratio"],
                    row["velocity_adjusted_score"], row["percentile"], row["baseline_sample_size"],
                    row["baseline_median_views"], row["baseline_median_views_per_day"],
                    row["eligibility_reason"], row["provisional"], json.dumps(row)))
            for topic in result["topics"]:
                self.connection.execute("INSERT INTO topic_groups VALUES (?,?,?)",
                                        (run_id, topic["theme"], json.dumps(topic)))

            if 'cohort_summaries' in result:
                encode=lambda value:json.dumps(value,ensure_ascii=False,allow_nan=False)
                self.connection.execute('INSERT INTO radar_market_runs VALUES (?,?,?,?,?)',(run_id,result['competitor_config_version'],result['cohort_config_version'],result['scoring_version'],encode(result['metadata']['market_config'])))
                for r in result['videos']:
                    self.connection.execute('INSERT INTO radar_opportunities VALUES (?,?,?,?,?,?,?,?,?)',(run_id,r['video_id'],r['market_cohort'],r['source_role'],r['researchability_score'],r['normalized_radar_signal'],r['cross_cohort_support'],r['opportunity_score'],encode(r)))
                for c in result['cohort_summaries']:
                    self.connection.execute('INSERT INTO radar_cohort_summaries VALUES (?,?,?)',(run_id,c['market_cohort'],encode(c)))
                for signal in result['cross_cohort_signals']:
                    self.connection.execute('INSERT INTO radar_cross_cohort_signals VALUES (?,?,?,?,?)',(run_id,signal['canonical_topic'],signal['independent_channel_count'],signal['vendor_channel_count'],encode(signal)))
