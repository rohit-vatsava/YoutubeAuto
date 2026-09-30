"""Append-only local production and performance records; no optimizer or source writes."""
import json,sqlite3,hashlib
from datetime import datetime,timezone
from pathlib import Path

class Store:
    def __init__(self,path):
        path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(path);self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES(1);
        CREATE TABLE IF NOT EXISTS productions(video_id TEXT PRIMARY KEY,script_id TEXT NOT NULL,revision INTEGER NOT NULL,spec TEXT NOT NULL,creative_dna TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS performance(video_id TEXT NOT NULL REFERENCES productions,platform TEXT NOT NULL,measurement_window TEXT NOT NULL,measured_at TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(video_id,platform,measurement_window,measured_at));
        CREATE TABLE IF NOT EXISTS preferences(version TEXT PRIMARY KEY,parent_version TEXT REFERENCES preferences,created_at TEXT NOT NULL,sample_size INTEGER NOT NULL,provenance TEXT NOT NULL,parameters TEXT NOT NULL);
        CREATE TRIGGER IF NOT EXISTS immutable_productions BEFORE UPDATE ON productions BEGIN SELECT RAISE(ABORT,'immutable production'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_performance BEFORE UPDATE ON performance BEGIN SELECT RAISE(ABORT,'immutable metric snapshot'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_preferences BEFORE UPDATE ON preferences BEGIN SELECT RAISE(ABORT,'immutable preferences'); END;
        CREATE TRIGGER IF NOT EXISTS no_delete_preferences BEFORE DELETE ON preferences BEGIN SELECT RAISE(ABORT,'retain preference history'); END;
        ''')
    def close(self):self.db.close()
    def save_production(self,spec):
        values=(spec['video_id'],spec['script_id'],spec['revision'],json.dumps(spec,sort_keys=True),json.dumps(spec['creative_dna'],sort_keys=True))
        row=self.db.execute('SELECT video_id,script_id,revision,spec,creative_dna FROM productions WHERE video_id=?',(spec['video_id'],)).fetchone()
        if row:
            if tuple(row)!=values:raise ValueError('Conflicting immutable production')
            return
        with self.db:self.db.execute('INSERT INTO productions VALUES(?,?,?,?,?)',values)
    def save_performance(self,record):
        r=record.to_dict();key=(r['video_id'],r['platform'],r['measurement_window'],r['measured_at']);text=json.dumps(r,sort_keys=True)
        old=self.db.execute('SELECT payload FROM performance WHERE video_id=? AND platform=? AND measurement_window=? AND measured_at=?',key).fetchone()
        if old:
            if old[0]!=text:raise ValueError('Conflicting metric snapshot')
            return
        with self.db:self.db.execute('INSERT INTO performance VALUES(?,?,?,?,?)',key+(text,))
    def joined(self,platform=None,window=None):
        rows=self.db.execute('SELECT p.video_id,p.creative_dna,m.platform,m.measurement_window,m.measured_at,m.payload FROM productions p JOIN performance m USING(video_id) ORDER BY m.measured_at')
        return [dict(video_id=r[0],creative_dna=json.loads(r[1]),platform=r[2],measurement_window=r[3],measured_at=r[4],performance=json.loads(r[5]),note='Observational only; not causal. Compare equal platform/window definitions.') for r in rows if (platform is None or r[2]==platform) and (window is None or r[3]==window)]
    def save_preferences(self,parameters,provenance,sample_size,parent_version=None):
        allowed={'topic_weights','hook_priors','duration_targets','scene_priors','payoff_timing','production_preferences'}
        if not parameters or not set(parameters)<=allowed:raise ValueError('Only versioned creative parameters may be stored; never executable code')
        if not provenance or sample_size<10:raise ValueError('Provenance and minimum 10 samples required')
        def numeric_tree(value):
            import math
            if isinstance(value,dict):return all(isinstance(k,str) and numeric_tree(v) for k,v in value.items())
            if isinstance(value,list):return all(numeric_tree(v) for v in value)
            return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
        if not numeric_tree(parameters):raise ValueError('Preference values must be finite numeric data, never source or executable instructions')
        now=datetime.now(timezone.utc).isoformat();version=hashlib.sha256(json.dumps([parameters,provenance,parent_version,now],sort_keys=True).encode()).hexdigest()[:20]
        with self.db:self.db.execute('INSERT INTO preferences VALUES(?,?,?,?,?,?)',(version,parent_version,now,sample_size,json.dumps(provenance),json.dumps(parameters)))
        return version
    def preferences(self,version):
        row=self.db.execute('SELECT parameters FROM preferences WHERE version=?',(version,)).fetchone()
        if not row:raise ValueError('Unknown preference version')
        return json.loads(row[0])  # Explicit version selection makes rollback reversible; no automatic activation.
