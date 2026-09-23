"""Offline validation and provenance checks for saved planning-stage resume."""
from copy import deepcopy
import json
import re
from .models import digest
from .pivot_scope import validate_candidate,validated_angle
from .claims import time


def load_resume(root,script_id,db,now,config):
    if not re.fullmatch(r'script-[a-zA-Z0-9-]+',script_id):raise ValueError('Invalid script ID')
    folder=root/script_id
    def read(name):return json.loads((folder/(name+'.json')).read_text())
    run=read('run');packet=read('research_packet');selected=read('idea');candidate=read('angle_candidate') if (folder/'angle_candidate.json').exists() else None
    if run['script_id']!=script_id or run['research_run_id']!=packet['research_run_id']:raise ValueError('Resume run provenance mismatch')
    if not packet.get('pivot_acceptance') or packet['research_status']!='SUFFICIENT':raise ValueError('Resume requires an accepted-pivot evidence packet')
    if read('script') is not None:raise ValueError('Minimal resume supports runs stopped before outline generation only')
    row=db.connection.execute('SELECT r.selected_snapshot,p.payload,s.payload FROM research_runs_v3 r JOIN research_packets p USING(research_run_id) JOIN script_runs s USING(script_run_id) WHERE r.research_run_id=?',(run['research_run_id'],)).fetchone()
    if not row or digest(json.loads(row[0]))!=digest(selected) or digest(json.loads(row[1]))!=digest(packet):raise ValueError('Resume artifacts differ from database provenance')
    stored=json.loads(row[2]).get('generation_candidates',[])
    if candidate is None:
        saved_angle=read('angle')
        if digest(saved_angle)!=digest(json.loads(row[2]).get('angle')):raise ValueError('Saved angle differs from database provenance')
        candidate=dict(candidate_id='reused-angle',raw_generated_content=saved_angle)
    elif not any(c['candidate_id']==candidate['candidate_id'] and digest(c['raw_generated_content'])==digest(candidate['raw_generated_content']) for c in stored):
        raise ValueError('Persisted angle candidate differs from database audit')
    sources=read('sources')
    if digest(sources)!=digest(packet['source_records']):raise ValueError('Resume sources differ from evidence packet')
    for source in sources:
        if source['source_id'] not in {sid for c in packet['claims'] for sid in c['evidence_ids']}:continue
        age=(time(now)-time(source['retrieved_at'])).total_seconds()/86400
        if not 0<=age<=config['freshness_window_days']:raise ValueError('Resume evidence is stale; no model call made')
    report=validate_candidate(candidate['raw_generated_content'],packet,'angle_refinement',candidate['candidate_id'])
    if report['result']!='PASS' or report['next_status']!='CONTINUE':
        raise ValueError('Resume scope rejected before any model call: '+json.dumps(report['rejected_spans'],ensure_ascii=False))
    angle=validated_angle(candidate['raw_generated_content'],report)
    allowed={c['claim_id'] for c in packet['claims'] if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')}
    if not angle.get('evidence_basis') or not set(angle['evidence_basis'])<=allowed or angle.get('originality_status')=='REJECT':raise ValueError('Resume angle cannot proceed')
    existing=read('angle')
    if existing is not None and digest(existing)!=digest(angle):raise ValueError('Existing angle differs from validated candidate')
    outline=None;outline_report=None
    if (folder/'outline_candidate.json').exists():
        item=read('outline_candidate')
        if item.get('stage')!='script_outline' or not any(c['candidate_id']==item['candidate_id'] and digest(c['raw_generated_content'])==digest(item['raw_generated_content']) for c in stored):
            raise ValueError('Persisted outline differs from database audit')
        outline_report=validate_candidate(item['raw_generated_content'],packet,'script_outline',item['candidate_id'])
        if outline_report['result']!='PASS' or outline_report['next_status']!='CONTINUE':
            raise ValueError('Resume outline scope rejected before any model call')
        outline=deepcopy(item['raw_generated_content'])
        if read('outline') is not None and digest(read('outline'))!=digest(outline):raise ValueError('Existing outline differs from validated candidate')
    elif read('outline') is not None:
        outline=read('outline')
        if digest(outline)!=digest(json.loads(row[2]).get('outline')):raise ValueError('Saved outline differs from database provenance')
        outline_report=validate_candidate(outline,packet,'script_outline','reused-outline')
        if outline_report['result']!='PASS' or outline_report['next_status']!='CONTINUE':raise ValueError('Saved outline scope rejected')
    generation=None
    if (folder/'script_candidate.json').exists():
        item=read('script_candidate')
        if item.get('stage')!='script_generation' or not any(c['candidate_id']==item['candidate_id'] and digest(c['raw_generated_content'])==digest(item['raw_generated_content']) for c in stored):
            raise ValueError('Persisted generation differs from database audit')
        if outline is None:raise ValueError('Saved generation requires a validated outline')
        generation=deepcopy(item['raw_generated_content'])
        from .hook_scope import validate_hooks
        hook_report=validate_hooks(generation.get('hook_candidates',[]),packet,item['candidate_id'])
        if hook_report['result']!='PASS':raise ValueError('No surviving saved hooks; no model call made')
    return dict(generation=generation,outline=outline,outline_validation=outline_report,folder=folder,packet=packet,selected=selected,sources=sources,run=run,angle=angle,
                candidate=deepcopy(candidate),validation=report,plan=read('research_plan'))


def promote(resume):
    # Only angle.json is promoted in the original directory. Candidate, original
    # validation, cost, readiness and audit artifacts remain byte-for-byte intact.
    (resume['folder']/'angle.json').write_text(json.dumps(resume['angle'],indent=2,ensure_ascii=False)+'\n')
