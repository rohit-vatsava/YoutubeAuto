import json
from datetime import timedelta

TABLES = ('idea_scores', 'idea_sources', 'idea_candidates', 'trend_cluster_videos', 'trend_clusters',
          'story_briefs', 'evidence_sources', 'transcripts', 'intelligence_candidates')


def persist(db, result):
    run = result['intelligence_run_id']
    metadata = result['metadata']
    source_date = min([result['generated_at']] + [v['observed_at'] for v in result['candidates']])
    encode = lambda x: json.dumps(x, ensure_ascii=False, allow_nan=False)
    with db.connection:
        db.connection.execute('INSERT INTO intelligence_runs VALUES (?,?,?,?,?,?,0,?)',
                              (run, result['radar_run_id'], result['generated_at'], source_date,
                               metadata['mode'], metadata['status'], encode(metadata)))
        for v in result['candidates']:
            db.connection.execute('INSERT INTO intelligence_candidates VALUES (?,?,?,?,?)',
                                  (run, v['video_id'], result['radar_run_id'], v['snapshot_hash'], encode(v)))
        for vid, t in result['transcripts'].items():
            db.connection.execute('INSERT INTO transcripts VALUES (?,?,?,?,?,?,?,?)',
                                  (run, vid, t['transcript_status'], t['provider_name'], t['provider_version'],
                                   t['content_hash'], t['retrieved_at'], encode(t)))
        for b in result['story_briefs']:
            db.connection.execute('INSERT INTO story_briefs VALUES (?,?,?,?)',
                                  (run, b['video_id'], result['radar_run_id'], encode(b)))
            for e in b['source_evidence']:
                db.connection.execute('INSERT INTO evidence_sources VALUES (?,?,?,?)',
                                      (run, b['video_id'], e['evidence_id'], encode(e)))
        for c in result['trend_clusters']:
            db.connection.execute('INSERT INTO trend_clusters VALUES (?,?,?)', (run,c['cluster_id'],encode(c)))
            db.connection.executemany('INSERT INTO trend_cluster_videos VALUES (?,?,?)',
                                      [(run,c['cluster_id'],v) for v in c['supporting_video_ids']])
        for idea in result['ideas']:
            db.connection.execute('INSERT INTO idea_candidates VALUES (?,?,?,?,?,?)',
                                  (run,idea['idea_id'],idea['production_ready'],idea['similarity_status'],idea['category'],encode(idea)))
            db.connection.executemany('INSERT INTO idea_sources VALUES (?,?,?)',
                                      [(run,idea['idea_id'],v) for v in idea['source_video_ids']])
            scores = idea['scores']
            db.connection.execute('INSERT INTO idea_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                  (run,idea['idea_id'],idea['scoring_version'],
                                   *[scores[k] for k in ('DemandSignal','Freshness','Originality','AudienceFit','ProductionFit','EvidenceQuality','Expandability','SaturationRisk')],
                                   idea['idea_score'],encode(idea['score_rationale'])))


def expire(db, now):
    """Keep minimal audit receipts, not expired API snapshots/derived source payloads."""
    cutoff = (now-timedelta(days=30)).isoformat()
    rows = list(db.connection.execute("SELECT intelligence_run_id FROM intelligence_runs WHERE mode != 'synthetic' AND expired=0 AND source_observed_at<=?", (cutoff,)))
    with db.connection:
        for row in rows:
            run = row[0]
            for table in TABLES:
                db.connection.execute(f'DELETE FROM {table} WHERE intelligence_run_id=?', (run,))
            db.connection.execute("UPDATE intelligence_runs SET expired=1,status='expired',payload=? WHERE intelligence_run_id=?",
                                  ('{"retention":"Source payloads expired; provenance receipt retained"}', run))
    return [r[0] for r in rows]
