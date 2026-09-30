"""Append-only sentence text edits followed by review only. No generator/provider."""
from copy import deepcopy
from pathlib import Path
import json
import re
from .models import digest
from .generation import refresh_script_text,scope_propositions
from .pivot_scope import validate_candidate
from .claims import time
from . import storage

def read(path):return json.loads(path.read_text())
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
def folder_for(root,script_id,revision):
    if not re.fullmatch(r'script-[a-zA-Z0-9-]+',script_id):raise ValueError('Invalid script ID')
    return Path(root)/script_id/'editorial-revisions'/str(revision)

def source(root,script_id,db):
    folder=folder_for(root,script_id,1).parent.parent
    data={n:read(folder/(n+'.json')) for n in ('run','idea','research_packet','sources','angle','outline','script')}
    run=data['run'];draft=data['script'];packet=data['research_packet']
    if not draft or run['script_id']!=script_id or draft['script_id']!=script_id or draft['research_packet_id']!=packet['research_packet_id']:
        raise ValueError('Invalid saved draft lineage')
    row=db.connection.execute('SELECT payload FROM script_drafts WHERE script_run_id=? AND revision=?',(script_id,draft['revision'])).fetchone()
    if not row or digest(read_json(row[0]))!=digest(draft):raise ValueError('Saved script differs from database')
    row=db.connection.execute('SELECT payload FROM research_packets WHERE research_run_id=?',(run['research_run_id'],)).fetchone()
    if not row or digest(read_json(row[0]))!=digest(packet):raise ValueError('Research packet differs from database')
    row=db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(script_id,)).fetchone()
    payload=read_json(row[0])
    for key in ('angle','outline'):
        if digest(payload.get(key))!=digest(data[key]):raise ValueError('Saved '+key+' differs from database')
    row=db.connection.execute('SELECT selected_snapshot FROM research_runs_v3 WHERE research_run_id=?',(run['research_run_id'],)).fetchone()
    if not row or digest(read_json(row[0]))!=digest(data['idea']):raise ValueError('Selection differs from database')
    if digest(data['sources'])!=digest(packet['source_records']):raise ValueError('Source snapshot mismatch')
    return data,payload

def read_json(value):return json.loads(value)

def apply_sentence_moves(draft,moves):
    """Move existing body objects, sequentially, before an existing target anchor."""
    if not isinstance(moves,list):raise ValueError('sentence_moves must be a list')
    if not moves:return
    sections=draft['sections']
    names=[s['name'] for s in sections]
    ids=[r['sentence_id'] for sec in sections for r in sec['sentences']]
    if len(names)!=len(set(names)) or len(ids)!=len(set(ids)):
        raise ValueError('Ambiguous section names or duplicate sentence IDs')
    seen=set()
    for move in moves:
        if not isinstance(move,dict) or set(move)!={'sentence_id','target_section','before_sentence_id'} or any(not isinstance(v,str) or not v for v in move.values()):
            raise ValueError('Each move requires sentence_id, target_section, before_sentence_id only')
        sid=move['sentence_id'];anchor=move['before_sentence_id']
        if sid in seen:raise ValueError('Duplicate move for sentence ID')
        seen.add(sid)
        origin=next((sec for sec in sections if any(r['sentence_id']==sid for r in sec['sentences'])),None)
        target=next((sec for sec in sections if sec['name']==move['target_section']),None)
        if origin is None:raise ValueError('Unknown sentence ID')
        if target is None:raise ValueError('Unknown target section')
        if origin['name'].upper()=='HOOK' or target['name'].upper()=='HOOK' or sid=='selected-hook':
            raise ValueError('Selected hook is locked')
        if sid==anchor or not any(r['sentence_id']==anchor for r in target['sentences']):
            raise ValueError('Invalid before_sentence_id anchor')
        row=next(r for r in origin['sentences'] if r['sentence_id']==sid)
        origin['sentences'].remove(row)
        index=next(i for i,r in enumerate(target['sentences']) if r['sentence_id']==anchor)
        target['sentences'].insert(index,row)
    after=[r['sentence_id'] for sec in sections for r in sec['sentences']]
    if sorted(after)!=sorted(ids):raise ValueError('Move changed sentence identities')


def apply_edits(original,edits,config):
    """Construct an edited copy without persistence or external calls."""
    draft=deepcopy(original)
    if not isinstance(edits,dict) or not edits:raise ValueError('Edits must map sentence IDs to replacement text')
    editable={s['sentence_id']:s for sec in draft['sections'] if sec['name'].upper()!='HOOK' for s in sec['sentences']}
    metadata={'visual_note_replacements','pronunciation_notes','sentence_moves'}
    body_edits={k:v for k,v in edits.items() if k not in metadata}
    if not set(body_edits)<=editable.keys():raise ValueError('Only existing body sentence IDs can be edited; hook is locked')
    for sid,text in body_edits.items():
        if not isinstance(text,str) or not text.strip():raise ValueError('Replacement text must be nonempty')
        editable[sid]['text']=text
    if 'visual_note_replacements' in edits:
        replacements=edits['visual_note_replacements']
        if not isinstance(replacements,dict):raise ValueError('visual_note_replacements must be an index-to-text object (zero-based)')
        for index,text in replacements.items():
            if not isinstance(index,str) or not re.fullmatch(r'0|[1-9][0-9]*',index) or int(index)>=len(draft.get('visual_notes',[])):
                raise ValueError('Invalid zero-based visual note index')
            if not isinstance(text,str) or not text.strip():raise ValueError('Visual note must be nonempty text')
            draft['visual_notes'][int(index)]=text
    if 'pronunciation_notes' in edits:
        notes=edits['pronunciation_notes']
        if not isinstance(notes,list) or any(not isinstance(x,str) or not x.strip() for x in notes):
            raise ValueError('pronunciation_notes must be a list of nonempty strings')
        draft['pronunciation_notes']=deepcopy(notes)
    apply_sentence_moves(draft,edits.get('sentence_moves',[]))
    if draft==original:raise ValueError('No text changed')
    if body_edits or edits.get('sentence_moves'):refresh_script_text(draft,config)
    return draft


def create(root,script_id,edits,db,now,config,base_revision=None):
    data,payload=source(root,script_id,db);original=data['script']
    if base_revision is not None:
        if type(base_revision) is not int or base_revision < 1:raise ValueError('Invalid base revision')
        if base_revision != original['revision']:
            original,_,_=saved_revision(root,script_id,base_revision,db,data,payload)
    draft=apply_edits(original,edits,config)
    revision=db.connection.execute('SELECT MAX(revision) FROM script_drafts WHERE script_run_id=?',(script_id,)).fetchone()[0]+1
    draft['revision']=revision
    report=validate_candidate({'propositions':scope_propositions(draft)},data['research_packet'],'script_generation','editorial-'+str(revision))
    if report['result']!='PASS' or report['next_status']!='CONTINUE':raise ValueError('Editorial revision failed current scope validation: '+json.dumps(report['rejected_spans'],ensure_ascii=False))
    folder=folder_for(root,script_id,revision);folder.mkdir(parents=True,exist_ok=False)
    manifest=dict(script_id=script_id,revision=revision,parent_revision=original['revision'],created_at=now,
        research_run_id=data['run']['research_run_id'],draft_hash=digest(draft),
        preserved_hashes={n:digest(data[n]) for n in ('idea','research_packet','sources','angle','outline')},
        selected_hook_hash=digest(original['selected_hook']),configuration=deepcopy(config),
        invalidated=['fact_check','quality_review','readiness'],status='AWAITING_FACT_CHECK')
    with db.connection:
        storage.save_draft(db,draft)
        payload.setdefault('editorial_revisions',{})[str(revision)]=manifest
        db.connection.execute('UPDATE script_runs SET payload=? WHERE script_run_id=?',(storage.encode(payload),script_id))
    for name,value in [('script',draft),('manifest',manifest),('scope_validation',report),
                       ('fact_check',None),('quality_review',None),
                       ('readiness',{'status':'AWAITING_FACT_CHECK','reasons':['SCRIPT_TEXT_CHANGED']})]:
        write(folder/(name+'.json'),value)
    return manifest,folder

def saved_revision(root,script_id,revision,db,data,payload):
    """Verify an immutable base, including already-reviewed revisions."""
    folder=folder_for(root,script_id,revision);manifest=read(folder/'manifest.json');draft=read(folder/'script.json')
    if digest(manifest)!=digest(payload.get('editorial_revisions',{}).get(str(revision))):raise ValueError('Revision manifest differs from database')
    row=db.connection.execute('SELECT payload FROM script_drafts WHERE script_run_id=? AND revision=?',(script_id,revision)).fetchone()
    if not row or digest(read_json(row[0]))!=digest(draft) or digest(draft)!=manifest['draft_hash']:raise ValueError('Revision differs from database')
    if any(digest(data[n])!=h for n,h in manifest['preserved_hashes'].items()):raise ValueError('Parent provenance changed')
    if digest(draft['selected_hook'])!=manifest['selected_hook_hash']:raise ValueError('Selected hook changed')
    return draft,manifest,folder

def load(root,script_id,revision,db,now,config):
    data,payload=source(root,script_id,db)
    draft,manifest,folder=saved_revision(root,script_id,revision,db,data,payload)
    if str(revision) in payload.get('editorial_revision_reviews',{}):raise ValueError('This revision already has a review attempt; create a new revision')
    for table in ('script_fact_checks','script_quality_reviews'):
        if db.connection.execute(f'SELECT 1 FROM {table} WHERE script_run_id=? AND revision=?',(script_id,revision)).fetchone():
            raise ValueError('This revision has already been reviewed; create a new revision instead')
    for s in data['sources']:
        age=(time(now)-time(s['retrieved_at'])).total_seconds()/86400
        if not 0<=age<=config['freshness_window_days']:raise ValueError('Saved evidence is stale')
    report=validate_candidate({'propositions':scope_propositions(draft)},data['research_packet'],'script_generation','editorial-'+str(revision))
    if report['result']!='PASS' or report['next_status']!='CONTINUE':raise ValueError('Current scope validation rejects revision')
    return dict(data=data,draft=draft,manifest=manifest,folder=folder,scope_validation=report)

def review(loaded,db,checker,reviewer,budget,now,config):
    from .fact_check import validate_check
    from .quality import review_quality
    from .readiness import decide
    data=loaded['data'];draft=deepcopy(loaded['draft']);folder=loaded['folder']
    check=None;quality=None;failures=[]
    budget.finish_research()
    try:
        with budget.stage('fact_check_cost'):
            check=validate_check(checker.check(draft,data['research_packet'],data['angle'],now),draft,data['research_packet'],now)
        storage.save_review(db,'script_fact_checks',check);write(folder/'fact_check.json',check)
        if check['verdict'] in ('PASS','PASS_WITH_MINOR_EDITS'):
            with budget.stage('quality_review_cost'):
                quality=review_quality(reviewer.review(draft,data['research_packet'],data['idea']),draft)
            storage.save_review(db,'script_quality_reviews',quality);write(folder/'quality_review.json',quality)
        readiness=decide(data['research_packet'],draft,check,quality,data['angle'],config)
    except Exception as exc:
        failures=[dict(stage='editorial_revision_review',error=type(exc).__name__)]
        readiness=dict(status='REVIEW_INCOMPLETE',reasons=['REVIEW_EXECUTION_FAILED'])
    costs=budget.record.to_dict()
    for name,value in [('readiness',readiness),('costs',costs),('failures',failures)]:
        write(folder/(name+'.json'),value)
    # Parent artifacts and prior review rows remain immutable; revision results live separately.
    row=db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(draft['script_id'],)).fetchone()
    payload=read_json(row[0]);payload.setdefault('editorial_revision_reviews',{})[str(draft['revision'])]=dict(
        readiness=readiness,costs=costs,failures=failures,checked_at=now)
    with db.connection:db.connection.execute('UPDATE script_runs SET payload=? WHERE script_run_id=?',(storage.encode(payload),draft['script_id']))
    return dict(readiness=readiness,cost=costs,failures=failures)
