"""Explicit quality-only continuation; historical review artifacts are immutable."""
import json
from copy import deepcopy
from .editorial_revision import source,saved_revision,read,write
from .models import digest
from .fact_check import validate_check
from .generation import scope_propositions
from .pivot_scope import validate_candidate
from .quality import review_quality
from .readiness import decide
from . import storage


def prepare(root,script_id,revision,db,now,config):
    data,payload=source(root,script_id,db)
    draft,manifest,folder=saved_revision(root,script_id,revision,db,data,payload)
    if str(revision) in payload.get('editorial_quality_continuations',{}) or (folder/'quality-continuation').exists():raise ValueError('Quality continuation already attempted')
    if read(folder/'quality_review.json') is not None or db.connection.execute(
            'SELECT 1 FROM script_quality_reviews WHERE script_run_id=? AND revision=?',(script_id,revision)).fetchone():
        raise ValueError('Quality review already exists')
    if read(folder/'readiness.json')['status'] in ('READY_FOR_PRODUCTION','REJECTED','EDITORIAL_REVIEW'):
        raise ValueError('Readiness is final')
    raw=read(folder/'fact_check.json')
    if not raw:raise ValueError('Missing fact-check')
    row=db.connection.execute('SELECT payload FROM script_fact_checks WHERE script_run_id=? AND revision=?',(script_id,revision)).fetchone()
    if not row or digest(json.loads(row[0]))!=digest(raw):raise ValueError('Fact-check differs from database')
    if raw.get('script_id')!=script_id or raw.get('revision')!=revision:raise ValueError('Fact-check provenance mismatch')
    scope=validate_candidate({'propositions':scope_propositions(draft)},data['research_packet'],'script_generation','quality-continuation')
    if scope['result']!='PASS' or scope['next_status']!='CONTINUE':raise ValueError('Current scope validation failed')
    # Recompute from the canonical original model verdict, not an external PASS file.
    check=validate_check(deepcopy(raw),draft,data['research_packet'],now)
    if check['verdict']!='PASS' or check['deterministic_issues'] or check['blocking_issues']:
        raise ValueError('Validated fact-check must PASS without blocking or deterministic issues')
    return dict(data=data,draft=draft,folder=folder,check=check,original_check=raw,
                provenance=dict(source='deterministic_revalidation',revalidated_at=now,
                    no_new_model_call=True,original_fact_check_hash=digest(raw),
                    draft_hash=digest(draft),research_packet_hash=digest(data['research_packet'])),
                eligible_to_continue=True,next_stage='QUALITY_REVIEW',fact_check_call_required=False)


def continue_quality(loaded,db,reviewer,budget,now,config):
    # An exclusive attempt directory also prevents duplicate calls after a crash.
    folder=loaded['folder']/'quality-continuation';folder.mkdir(exist_ok=False)
    write(folder/'fact_check.json',loaded['check']);write(folder/'provenance.json',loaded['provenance'])
    data=loaded['data'];draft=loaded['draft'];failures=[];quality=None
    budget.finish_research()
    try:
        with budget.stage('quality_review_cost'):
            quality=review_quality(reviewer.review(draft,data['research_packet'],data['idea']),draft)
        storage.save_review(db,'script_quality_reviews',quality)
        readiness=decide(data['research_packet'],draft,loaded['check'],quality,data['angle'],config)
    except Exception as exc:
        failures=[dict(stage='quality_review',error=type(exc).__name__)]
        readiness=dict(status='REVIEW_INCOMPLETE',reasons=['QUALITY_REVIEW_EXECUTION_FAILED'])
    costs=budget.record.to_dict()
    for name,value in [('quality_review',quality),('readiness',readiness),('costs',costs),('failures',failures)]:write(folder/(name+'.json'),value)
    row=db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(draft['script_id'],)).fetchone()
    payload=json.loads(row[0]);payload.setdefault('editorial_quality_continuations',{})[str(draft['revision'])]=dict(
        provenance=loaded['provenance'],fact_check=loaded['check'],quality_review=quality,readiness=readiness,costs=costs,failures=failures)
    with db.connection:db.connection.execute('UPDATE script_runs SET payload=? WHERE script_run_id=?',(storage.encode(payload),draft['script_id']))
    return dict(readiness=readiness,costs=costs,failures=failures)
