"""Explicit, provenance-checked reuse of saved research. No research provider."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from .claims import validate_packet, time
from .hooks import mapping_errors
from .models import digest

FORBIDDEN=['LAUNCH_DATE','BREAKING_NEWS','AGI','SUPERIORITY','BENCHMARK',
           'COMPETITOR_COMPARISON','RELIABILITY','SAFETY_CONCLUSION']
SKIPPED=['story_resolution','discovery_search','source_fetch','research_synthesis']
STAGES=['angle_refinement','script_outline','script_generation (five hooks + hook scoring + script)',
        'independent_fact_check','editorial_quality_review','readiness_gates']


def read(path):return json.loads(path.read_text())


def load_candidate(folder, idea_id, reports_root, now, config):
    packet=read(folder/'research_packet.json');pivot=read(folder/'angle_pivot.json')
    if packet.get('idea_id')!=idea_id:raise ValueError('Pivot idea does not match requested idea')
    if pivot!=packet.get('angle_pivot'):raise ValueError('Pivot artifact differs from packet')
    if pivot.get('status')!='ANGLE_PIVOT_RECOMMENDED' or pivot.get('pivot_requires_new_research') is not False:
        raise ValueError('Pivot is not eligible for evidence-only acceptance')
    rid=packet.get('research_run_id')
    # Resolve provenance by the exact research-run identity, never by an unrelated latest run.
    original=None
    for path in sorted(reports_root.glob('script-*/research_packet.json')):
        saved=read(path)
        if saved and saved.get('research_run_id')==rid:original=path.parent;break
    if original is None:raise ValueError('Original research-run artifacts unavailable')
    selected=read(original/'idea.json');plan=read(original/'research_plan.json')
    sources=read(original/'sources.json');old=read(original/'research_packet.json')
    if selected['idea']['idea_id']!=idea_id or old['idea_id']!=idea_id:raise ValueError('Original idea provenance mismatch')
    for key in ('research_run_id','research_packet_id','radar_run_id','intelligence_run_id'):
        if packet.get(key)!=old.get(key):raise ValueError('Research lineage mismatch: '+key)
    if digest(packet['source_records'])!=digest(sources):
        # Validation may append assessment notes/scores, but fetched content cannot change.
        fields=('source_id','url','text','retrieved_at','publication_date','title','authority_type','source_owner')
        snapshot=lambda rows:sorted([{k:s.get(k) for k in fields} for s in rows],key=lambda s:s['source_id'])
        if snapshot(packet['source_records'])!=snapshot(sources):raise ValueError('Fetched evidence differs from original source records')
    replay=folder/'replay.json'
    if replay.exists():
        for name,expected in read(replay).get('original_sha256',{}).items():
            if name not in ('research_packet','research_plan','sources','idea','research_outcome'):raise ValueError('Invalid replay manifest')
            if hashlib.sha256((original/(name+'.json')).read_bytes()).hexdigest()!=expected:raise ValueError('Original replay provenance changed')
    # Recreate the validation from the original raw claims. Edited replay claims,
    # assessments or recommendations must never become a new authority.
    validated=validate_packet(old,deepcopy(sources),plan,selected)
    from .pivots import recommend_pivot
    regenerated=recommend_pivot(validated,plan,selected,read(original/'research_outcome.json'))
    if regenerated!=pivot:raise ValueError('Pivot cannot be reproduced from original fetched evidence')
    if digest(validated['claims'])!=digest(packet['claims']):raise ValueError('Repaired claims differ from reproducible validation')
    for source in sources:
        if source['source_id'] not in {i for c in validated['claims'] for i in c['evidence_ids']}:continue
        try:age=(time(now)-time(source['retrieved_at'])).total_seconds()/86400
        except (KeyError,ValueError,TypeError):raise ValueError('Evidence observation date missing') from None
        if not 0<=age<=config['freshness_window_days']:raise ValueError('Saved evidence is stale; new research required')
    return dict(packet=validated,pivot=pivot,selected=selected,plan=plan,sources=sources,
                artifact_path=str(folder.resolve()),artifact_hash=digest(packet),original_packet_hash=digest(old))


def load_latest(idea_id, root, now, config, explicit=None):
    if explicit:return load_candidate(explicit,idea_id,root/'scripts',now,config)
    candidates=[]
    for path in root.rglob('angle_pivot.json'):
        try:
            if not (path.parent/'research_packet.json').exists():continue
            packet=read(path.parent/'research_packet.json')
            if packet and packet.get('idea_id')==idea_id and read(path):
                candidates.append((packet.get('created_at',''),str(path.parent),path.parent))
        except (OSError,ValueError):continue
    for _,__,folder in sorted(candidates,reverse=True):
        try:return load_candidate(folder,idea_id,root/'scripts',now,config)
        except (ValueError,KeyError,OSError):continue
    raise ValueError('No compatible, reproducible, current research pivot found for this idea')


def accept(candidate, now):
    packet=deepcopy(candidate['packet']);pivot=candidate['pivot']
    if pivot.get('status')!='ANGLE_PIVOT_RECOMMENDED' or pivot.get('pivot_requires_new_research') is not False:
        raise ValueError('Pivot is not eligible for evidence-only acceptance')
    if packet.get('research_status')!='PARTIAL':raise ValueError('Expected a partial original research packet')
    claims=[c for c in packet['claims'] if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') and c.get('evidence_ids') and c.get('passages')]
    if not set(pivot['verified_claim_ids_supporting_pivot'])<={c['claim_id'] for c in claims if c['status']=='VERIFIED'}:
        raise ValueError('Pivot supporting claims are not verified')
    for c in claims:
        if c.get('verification_scope')!='SUPPORTED_WORDING_ONLY':raise ValueError('Pivot claim lacks an explicit verified scope')
        if c.get('claim_type') in ('IDENTITY_EVENT','IDENTITY_AVAILABILITY'):
            # The existence of documentation establishes identity, never its promotional superlative.
            c['supported_wording']=f"The publisher’s documentation identifies {candidate['plan']['canonical_topic']} as a model."
        c['text']=c['supported_wording']
    acceptance=dict(idea_id=packet['idea_id'],original_angle=pivot['original_angle'],accepted_angle=pivot['recommended_angle'],
        accepted_at=now,source_research_run_id=packet['research_run_id'],
        verified_claim_ids=[c['claim_id'] for c in claims if c['status']=='VERIFIED'],
        partially_verified_claim_ids=[c['claim_id'] for c in claims if c['status']=='PARTIALLY_VERIFIED'],
        allowed_claim_scope={c['claim_id']:dict(supported_wording=c['supported_wording'],limitations=c.get('limitations',[]),
            evidence_ids=c['evidence_ids'],passage_ids=[p['passage_id'] for p in c['passages']]) for c in claims},
        forbidden_claims=list(dict.fromkeys(FORBIDDEN+pivot.get('forbidden_claims',[]))),requires_new_research=False,editorial_status='ACCEPTED',
        source_artifact_path=candidate['artifact_path'],source_artifact_hash=candidate['artifact_hash'])
    # This is a NEW packet for the accepted scope, not a promotion of the original comparison.
    scoped=dict(idea_id=packet['idea_id'],topic=candidate['plan']['canonical_topic'],claims=claims,
        source_records=deepcopy(candidate['sources']),research_status='SUFFICIENT',
        original_research_status=packet['research_status'],original_angle_outcome='ANGLE_UNSUPPORTED',
        source_research_run_id=packet['research_run_id'],pivot_acceptance=acceptance,
        final_research_question=pivot['recommended_angle'],safe_angle=pivot['recommended_angle'],
        canonical_story_resolved=True,remaining_questions_material=False,research_gaps=[],unresolved_requirements=[],
        core_claim_ids=pivot['verified_claim_ids_supporting_pivot'],
        freshness={'mode':'EVERGREEN','established':True,'event_date':'','evidence_ids':sorted({i for c in claims for i in c['evidence_ids']})},
        why_now='Evergreen documentation explainer using saved observations; no launch timing established.',
        confirmed_story=pivot['recommended_angle'],angles_to_avoid=acceptance['forbidden_claims'],
        verified_claims=[c for c in claims if c['status']=='VERIFIED'],
        uncertain_claims=[c for c in claims if c['status']=='PARTIALLY_VERIFIED'],
        evidence_passages=packet['evidence_passages'])
    return acceptance,scoped


def scope_issues(value, packet, *, draft=False):
    """Deterministic denial rules complement (never replace) semantic fact checking."""
    acceptance=packet.get('pivot_acceptance')
    if not acceptance:return []
    allowed=set(acceptance['allowed_claim_scope']);issues=[]
    forbidden=r'\b(launched|released|announced|new today|AGI|artificial general intelligence|beats|outperforms|superior|best model|most capable|benchmark|more reliable|guaranteed|safest|safer than|changes everything|the future is here)\b'
    def walk(item):
        if isinstance(item,dict):
            if value.get('scope_contract_version')==2 and item.get('factual') is False and isinstance(item.get('text'),str):
                from .pivot_scope import classify
                if classify(dict(text=item['text'],factual=False),packet)['classification']=='NONFACTUAL_EDITORIAL':return
            for key,val in item.items():
                if key in ('claim_ids','evidence_basis','title_claim_ids') and (not isinstance(val,list) or not set(val)<=allowed):issues.append('NEW_UNSUPPORTED_CLAIM')
                if key not in ('do_not_say','original_proposed_angle','rationale','limitations','originality_rationale'):walk(val)
        elif isinstance(item,list):
            for x in item:walk(x)
        elif isinstance(item,str):
            if value.get('scope_contract_version')==2:
                from .scope_language import polarity
                from .pivot_scope import FORBIDDEN
                if any(p['polarity']=='ASSERTION' for p in polarity(item,FORBIDDEN)):issues.append('FORBIDDEN_PIVOT_CLAIM')
            elif re.search(forbidden,item,re.I):issues.append('FORBIDDEN_PIVOT_CLAIM')
    if draft and value.get('scope_contract_version')==2:
        # Only publishable draft surfaces; the accepted angle's caution lists and
        # validator self-check metadata are not new assertions in the script.
        walk({k:value[k] for k in ('title_working','sections','on_screen_text','hook_candidates','visual_notes','full_script') if k in value})
    else:walk(value)
    if draft:
        from .generation import sentences
        claims={c['claim_id']:c for c in packet['claims']}
        for item in sentences(value)+value.get('hook_candidates',[]):
            issues.extend(mapping_errors(item,packet))
            for cid in item.get('claim_ids',[]):
                c=claims.get(cid,{})
                if not any(p['passage_id'] in item.get('evidence_passage_ids',[]) and
                           p['source_id'] in item.get('source_ids',[]) and p['source_id'] in c.get('evidence_ids',[])
                           and p['relation']=='SUPPORTS' for p in c.get('passages',[])):
                    issues.append('CLAIM_SOURCE_PASSAGE_LINK_MISSING:'+cid)
    return sorted(set(issues))


def dry_run(candidate, config, now, output):
    acceptance,packet=accept(candidate,now)
    logical=5+3*config['max_revision_attempts']
    # API's existing 180KB payload bound, conservative byte-based reservation, full output cap.
    budget_config=deepcopy(config)
    from .costs import Budget
    budget=Budget(budget_config);budget.finish_research()
    per_call=budget.estimate(180000,payload_bytes=180000)
    report=dict(loaded_pivot=candidate['pivot'],allowed_claim_ids=list(acceptance['allowed_claim_scope']),
        forbidden_claim_categories=acceptance['forbidden_claims'],stages_skipped=SKIPPED,stages_that_would_run=STAGES,
        projected_model_calls={'initial':5,'with_one_editorial_revision':logical,'maximum_transport_attempts':logical*min(2,config['max_attempts'])},
        projected_maximum_cost_usd=config['max_model_cost_usd'],per_request_reservation_ceiling_usd=per_call,
        all_attempts_unconstrained_ceiling_usd=per_call*logical*min(2,config['max_attempts']),
        cost_note='Configured application admission cap includes unknown charges and retries; completion within this cap is not guaranteed.',
        structurally_safe_for_one_live_generation_test=True,production_readiness='NOT_EVALUATED',
        actual_model_calls=0,actual_search_calls=0,actual_fetch_calls=0,actual_cost_usd=0)
    output.mkdir(parents=True,exist_ok=True)
    for name,value in [('pivot_acceptance',acceptance),('accepted_research_packet',packet),('dry_run',report)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    return report
