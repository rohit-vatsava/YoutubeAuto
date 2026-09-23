import json
from .models import digest, GENERATION_VERSION
from .generation import sentences


def encode(value):return json.dumps(value,ensure_ascii=False,allow_nan=False)


def start(db,result,config,provider):
    s=result['selected']
    with db.connection:
        db.connection.execute('INSERT INTO research_runs_v3 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (result['research_run_id'],result['script_id'],s['radar_run_id'],s['intelligence_run_id'],s['idea']['idea_id'],
             provider,GENERATION_VERSION,digest(config),result['created_at'],s['source_observed_at'],result['mode'],encode(s),encode(result['plan']),encode({'status':'IN_PROGRESS'})))
        db.connection.execute('INSERT INTO script_runs VALUES (?,?,?,?)',(result['script_id'],result['research_run_id'],'IN_PROGRESS',encode({'created_at':result['created_at']})))


def save_research(db,result):
    rid=result['research_run_id'];packet=result.get('packet')
    with db.connection:
        for source in result['sources']:
            db.connection.execute('INSERT INTO research_sources VALUES (?,?,?)',(rid,source['source_id'],encode(source)))
        if packet:
            for c in packet['claims']:
                db.connection.execute('INSERT INTO research_claims VALUES (?,?,?)',(rid,c['claim_id'],encode(c)))
                for p in {p['passage_id']:p for p in c['passages']}.values():
                    db.connection.execute('INSERT INTO research_claim_evidence VALUES (?,?,?,?)',(rid,c['claim_id'],p['passage_id'],encode(p)))
            db.connection.execute('INSERT INTO research_packets VALUES (?,?,?)',(packet['research_packet_id'],rid,encode(packet)))
        db.connection.execute('UPDATE research_runs_v3 SET plan=? WHERE research_run_id=?',(encode(result['plan']),rid))
        db.connection.execute('UPDATE research_runs_v3 SET outcome=? WHERE research_run_id=?',(encode(dict(result['research_outcome'],story_resolution=result.get('story_resolution'))),rid))


def save_draft(db,draft):
    sid,rev=draft['script_id'],draft['revision']
    with db.connection:
        db.connection.execute('INSERT INTO script_drafts VALUES (?,?,?)',(sid,rev,encode(draft)))
        for h in draft['hook_candidates']:db.connection.execute('INSERT INTO script_hooks VALUES (?,?,?,?)',(sid,rev,h['hook_id'],encode(h)))
        for s in sentences(draft):db.connection.execute('INSERT INTO script_claim_map VALUES (?,?,?,?)',(sid,rev,s['sentence_id'],encode(s)))
        title={'sentence_id':'working-title','text':draft['title_working'],'claim_ids':draft['title_claim_ids'],'mapping_kind':'TITLE_CLAIM_REFERENCES'}
        db.connection.execute('INSERT INTO script_claim_map VALUES (?,?,?,?)',(sid,rev,'working-title',encode(title)))


def save_review(db,table,review):
    if table not in ('script_fact_checks','script_quality_reviews'):raise ValueError('Unknown review table')
    with db.connection:db.connection.execute(f'INSERT INTO {table} VALUES (?,?,?)',(review['script_id'],review['revision'],encode(review)))


def finish(db,result):
    with db.connection:
        db.connection.execute('UPDATE script_runs SET status=?,payload=? WHERE script_run_id=?',
                              (result['readiness']['status'],encode({'readiness':result['readiness'],'failures':result['failures'],'angle':result.get('angle'),'outline':result.get('outline'),'configuration':result['configuration'],'providers':result['providers'],'generation_candidates':result.get('generation_candidates',[]),'scope_validations':result.get('scope_validations',[]),'resume_metadata':result.get('resume_metadata'),'checkpoint':result.get('resume_snapshot'),'checkpoint_hash':digest(result['resume_snapshot']) if result.get('resume_snapshot') else None}),result['script_id']))
        db.connection.execute('INSERT INTO script_cost_records VALUES (?,?)',(result['script_id'],encode(result['cost'])))


def cached_result(db,selected,config,now):
    """Reuse only a complete, still-fresh exact idea/configuration result."""
    from .claims import time
    for row in db.connection.execute('SELECT r.*,s.status FROM research_runs_v3 r JOIN script_runs s USING(script_run_id) WHERE r.configuration_hash=? AND r.mode=? ORDER BY r.rowid DESC',(digest(config),'live')):
        if row['status']!='READY_FOR_PRODUCTION':continue
        prior=json.loads(row['selected_snapshot'])
        if prior['idea_snapshot_hash']!=selected['idea_snapshot_hash'] or prior['intelligence_run_id']!=selected['intelligence_run_id']:continue
        if row['status']!='READY_FOR_PRODUCTION':continue
        p=db.connection.execute('SELECT payload FROM research_packets WHERE research_run_id=?',(row['research_run_id'],)).fetchone()
        if not p:continue
        packet=json.loads(p[0])
        if 0 <= (time(now)-time(packet['freshness']['event_date'])).total_seconds()/86400 <= config['freshness_window_days']:
            return row['script_run_id']
    return None


def expire(db,now):
    """Delete expired derived payloads; keep IDs and dates as a minimal receipt."""
    from datetime import timedelta
    cutoff=(now-timedelta(days=30)).isoformat()
    rows=list(db.connection.execute("SELECT research_run_id,script_run_id FROM research_runs_v3 WHERE mode!='synthetic' AND source_observed_at<=?",(cutoff,)))
    with db.connection:
        for rid,sid in rows:
            for table in ('script_hooks','script_claim_map','script_fact_checks','script_quality_reviews','script_drafts','script_cost_records'):
                db.connection.execute(f'DELETE FROM {table} WHERE script_run_id=?',(sid,))
            for table in ('research_claim_evidence','research_claims','research_sources','research_packets'):
                db.connection.execute(f'DELETE FROM {table} WHERE research_run_id=?',(rid,))
            db.connection.execute("UPDATE script_runs SET status='EXPIRED',payload='{}' WHERE script_run_id=?",(sid,))
            db.connection.execute("UPDATE research_runs_v3 SET selected_snapshot='{}',plan='{}',outcome=? WHERE research_run_id=?",(encode({'status':'EXPIRED'}),rid))
    return [row[1] for row in rows]


def generation_checkpoint(db,result):
    """Commit diagnostics without schema changes; raw candidates retain their IDs."""
    with db.connection:
        row=db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(result['script_id'],)).fetchone()
        payload=json.loads(row[0]) if row else {}
        payload.update(resume_metadata=result.get('resume_metadata'),angle=result.get('angle'),generation_candidates=result.get('generation_candidates',[]),scope_validations=result.get('scope_validations',[]))
        db.connection.execute('UPDATE script_runs SET payload=? WHERE script_run_id=?',(encode(payload),result['script_id']))


class PipelinePaused(Exception):
    """Explicit test/operator checkpoint, not a content or provider failure."""


def boundary(db,result,stage):
    """Commit a successful stage before allowing the next one to execute."""
    from copy import deepcopy
    completed=result.setdefault('completed_stages',[])
    if stage in completed:return
    completed.append(stage)
    if result.get('resume_metadata'):
        executed=result['resume_metadata'].setdefault('boundaries_executed',[])
        executed.append(stage)
    snapshot=deepcopy({k:v for k,v in result.items() if not k.startswith('_') and k!='resume_snapshot'})
    result['resume_snapshot']=snapshot
    row=db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(result['script_id'],)).fetchone()
    payload=json.loads(row[0]) if row else {}
    payload['checkpoint']=snapshot;payload['checkpoint_hash']=digest(snapshot)
    with db.connection:db.connection.execute('UPDATE script_runs SET payload=? WHERE script_run_id=?',(encode(payload),result['script_id']))
    if result.get('_stop_after')==stage:raise PipelinePaused(stage)
