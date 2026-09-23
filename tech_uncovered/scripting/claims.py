from copy import deepcopy
import re
from datetime import datetime
from .models import stable_id
from .sources import independent_sources
from .passages import repair_documentation, locate, passage


def time(value):
    return datetime.fromisoformat(value.replace('Z','+00:00'))


def validate_packet(raw, sources, plan, selected):
    packet=deepcopy(raw);packet['evidence_link_diagnostics']=[];by_id={s['source_id']:s for s in sources};seen=set()
    for assessment in packet.get('source_assessments',[]):
        source=by_id.get(assessment.get('source_id'))
        if not source:continue
        source['notes']=list(dict.fromkeys(source.get('notes',[])+['Claim-relative model/fixture assessment: '+assessment.get('rationale','')]))
        if source.get('authority_type') in ('COMMUNITY','HOSTED_DOCUMENT'):
            assessment['source_type']='OTHER';assessment['primary_or_secondary']='SECONDARY'
        source['source_type']=assessment.get('source_type','OTHER')
        source['primary_or_secondary']=assessment.get('primary_or_secondary','UNKNOWN')
        for field in ('authority_score','freshness_score','relevance_score'):
            value=assessment.get(field,0)
            if isinstance(value,(int,float)) and 0<=value<=100:source[field]=value
        from .sources import priority
        source['source_priority']=priority(source)

    for claim in packet.get('claims',[]):
        if claim['claim_id'] in seen:raise ValueError('Duplicate research claim ID')
        seen.add(claim['claim_id']);valid=[]
        repair_documentation(claim,by_id,packet.get('source_assessments',[]),plan.get('canonical_topic',''))
        for p in claim.get('passages',[]):
            source=by_id.get(p['source_id'])
            if not source or source.get('acquisition_state')=='DISCOVERED':continue
            relation=p.get('relation');support='CONTRADICTING' if relation=='CONTRADICTS' else p.get('support_type','DIRECT')
            linked=locate(source,p.get('quote',p.get('text','')),claim['claim_id'],support)
            if not linked and claim.get('evidence_link_method')=='STRUCTURED_DOCUMENTATION_OBSERVATION':
                start=p.get('start_offset');end=p.get('end_offset')
                if isinstance(start,int) and isinstance(end,int) and 0<=start<end<=len(source['text']) and source['text'][start:end]==p.get('text'):
                    linked=passage(source,start,end,claim['claim_id'],support)
            if linked and relation in ('SUPPORTS','CONTRADICTS'):valid.append(linked)
        claim['passages']=valid
        supporting={p['source_id'] for p in valid if p['relation']=='SUPPORTS'}
        contrary={p['source_id'] for p in valid if p['relation']=='CONTRADICTS'}
        claim['evidence_ids']=sorted(supporting)
        claim['contradicting_evidence_ids']=sorted(contrary)
        if claim['contradicting_evidence_ids']:
            claim['status']='DISPUTED' if claim['evidence_ids'] else 'FALSE_OR_MISLEADING'
        elif not claim['evidence_ids'] or not claim.get('supported_wording'):
            claim['status']='UNVERIFIED'
        elif claim['status'] not in ('VERIFIED','PARTIALLY_VERIFIED'):
            claim['status']='UNVERIFIED'
        if claim['status']=='PARTIALLY_VERIFIED' and not claim.get('limitations'):claim['status']='UNVERIFIED'
        # Credibility is claim-relative and must have a documented assessment from synthesis.
        assessments=packet.get('source_assessments',[])
        credible={a['source_id'] for a in assessments if a.get('credible_for_claim_ids') and claim['claim_id'] in a['credible_for_claim_ids'] and a.get('rationale') and a.get('source_type') in ('OFFICIAL','PAPER','DOCUMENTATION','NEWS','INTERVIEW')}
        if not (credible & set(claim['evidence_ids'])) and claim['status'] in ('VERIFIED','PARTIALLY_VERIFIED'):
            claim['status']='UNVERIFIED';claim['limitations']=claim.get('limitations',[])+['No claim-relative credible source assessment']
        claim['passage_ids']=[p['passage_id'] for p in valid]
        if not claim['evidence_ids'] and re.search(r'\b(explicitly|directly|supports?|establish(?:es)?)\b',claim.get('rationale',''),re.I):
            packet['evidence_link_diagnostics'].append(dict(claim_id=claim['claim_id'],
                code='SUPPORT_RATIONALE_WITHOUT_LINKED_EVIDENCE',claim_type=claim.get('claim_type')))
    claims=packet.get('claims',[]);core=set(packet.get('core_claim_ids',[]))
    critical=[c for c in claims if c['materiality']=='CRITICAL' or c['claim_id'] in core]
    supported=bool(core) and core<=seen and bool(critical) and all(c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') for c in critical)
    fresh=packet.get('freshness',{});fresh_ok=False
    try:
        age=(time(plan['planned_at'])-time(fresh['event_date'])).total_seconds()/86400
        dated_ids={s['source_id'] for s in sources if s.get('publication_date') and 0 <= (time(plan['planned_at'])-time(s['publication_date'])).total_seconds()/86400 <= plan['freshness_requirement']['window_days']}
        core_evidence={i for c in critical if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') for i in c['evidence_ids']}
        fresh_ok=fresh.get('established') and 0<=age<=plan['freshness_requirement']['window_days'] and bool(set(fresh.get('evidence_ids',[])) & dated_ids & core_evidence)
    except (ValueError,TypeError,KeyError):pass
    fresh['established']=bool(fresh_ok);fresh['mode']=plan.get('freshness_requirement',{}).get('mode','NEWS_FRESHNESS');packet['freshness']=fresh
    news_ok=bool(fresh_ok)
    resolved={r['requirement_id'] for r in packet.get('requirement_resolutions',[]) if r.get('rationale') and r.get('claim_ids') and all(any(c['claim_id']==cid and c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') for c in claims) for cid in r['claim_ids'])}
    primary_ids={a['source_id'] for a in packet.get('source_assessments',[])
                 if a.get('primary_or_secondary')=='PRIMARY' and a.get('source_type') in ('OFFICIAL','DOCUMENTATION','PAPER')
                 and by_id.get(a['source_id'],{}).get('authority_type') not in ('COMMUNITY','HOSTED_DOCUMENT')
                 and by_id.get(a['source_id'],{}).get('eligible_for_primary_identity',True)}
    for requirement in plan.get('requirement_queue',[]):
        if requirement['category']!='PRIMARY_DOCUMENTATION':continue
        mappings=[r for r in packet.get('requirement_resolutions',[]) if r.get('requirement_id')==requirement['requirement_id']]
        claim_ids={cid for r in mappings for cid in r.get('claim_ids',[])}
        if not any(c['claim_id'] in claim_ids and c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')
                   and primary_ids & set(c['evidence_ids']) for c in claims):
            resolved.discard(requirement['requirement_id'])
    if plan.get('comparison_required'):
        comparison=packet.get('comparison_evidence',{})
        verified={c['claim_id']:c for c in claims if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')}
        def grounded(ids,term):
            return bool(ids and term and all(cid in verified for cid in ids) and any(
                term.casefold() in p['quote'].casefold() for cid in ids for p in verified[cid]['passages'] if p['relation']=='SUPPORTS'))
        selection=comparison.get('selection_claim_ids',[])
        candidate=grounded(selection,comparison.get('alternative','')) and grounded(selection,comparison.get('criterion',''))
        packet['comparison_candidate_grounded']=bool(candidate)
        left=comparison.get('subject_claim_ids',[]);right=comparison.get('alternative_claim_ids',[])
        comparable=bool(candidate and comparison.get('decision') and comparison.get('conditions') and comparison.get('rationale')
            and comparison.get('like_for_like') is True and grounded(left,plan['canonical_topic'])
            and grounded(right,comparison.get('alternative','')) and grounded(left,comparison.get('criterion',''))
            and grounded(right,comparison.get('criterion','')))
        packet['comparison_supported']=comparable
        if not comparable:
            blocked={q['requirement_id'] for q in plan.get('requirement_queue',[]) if q['category'].startswith('COMPARISON')}
            resolved-=blocked
    partial=set()
    for q in plan.get('requirement_queue',[]):
        if q['category']=='IDENTITY_EVENT' and not news_ok:
            mapped={cid for r in packet.get('requirement_resolutions',[]) if r['requirement_id']==q['requirement_id'] for cid in r.get('claim_ids',[])}
            if any(c['claim_id'] in mapped and c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') and primary_ids & set(c['evidence_ids']) for c in claims):
                partial.add(q['requirement_id']);resolved.discard(q['requirement_id'])
    packet['partially_resolved_requirement_ids']=sorted(partial)
    packet['requirement_statuses']=[dict(requirement_id=q['requirement_id'],category=q['category'],
        status='RESOLVED' if q['requirement_id'] in resolved else 'PARTIALLY_RESOLVED' if q['requirement_id'] in partial else 'UNRESOLVED') for q in plan.get('requirement_queue',[])]
    observed=[]
    for source in sources:
        try:
            age=(time(plan['planned_at'])-time(source['retrieved_at'])).total_seconds()/86400
            if source['source_id'] in primary_ids and 0<=age<=plan['freshness_requirement']['window_days'] and any(source['source_id'] in c['evidence_ids'] and c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') for c in claims):observed.append(source['source_id'])
        except (KeyError,ValueError,TypeError):pass
    packet['freshness_assessments']={'NEWS_FRESHNESS':{'established':news_ok},
        'PRODUCT_CURRENTNESS':{'established':bool(observed),'evidence_ids':observed,'scope':'Documentation observed at retrieval time; not launch timing'},
        'EVERGREEN':{'established':bool(observed),'evidence_ids':observed,'scope':'Attributed documentation observations only'}}
    if fresh['mode'] in ('PRODUCT_CURRENTNESS','EVERGREEN'):
        fresh_ok=bool(observed);fresh['established']=fresh_ok
    unresolved=[r['text'] for r in plan['requirements'] if r['requirement_id'] not in resolved]
    packet['resolved_requirement_ids']=sorted(resolved);packet['unresolved_requirements']=unresolved
    contradictions=any(c['status'] in ('DISPUTED','FALSE_OR_MISLEADING') for c in critical)
    sufficient=supported and fresh_ok and packet.get('canonical_story_resolved') and not packet.get('remaining_questions_material',True) and not packet.get('research_gaps') and not unresolved
    packet['research_status']='CONTRADICTED' if contradictions else 'SUFFICIENT' if sufficient else 'PARTIAL' if any(c['status'] in ('VERIFIED','PARTIALLY_VERIFIED') for c in claims) else 'INSUFFICIENT'
    packet['research_evidence_status']=packet['research_status']
    packet['angle_feasibility_status']='SUPPORTED' if sufficient else 'NOT_ESTABLISHED'
    packet.update(idea_id=selected['idea']['idea_id'],source_records=sources,
                  independent_source_count=len(independent_sources(sources)),
                  verified_claims=[c for c in claims if c['status']=='VERIFIED'],
                  uncertain_claims=[c for c in claims if c['status'] in ('PARTIALLY_VERIFIED','UNVERIFIED')],
                  disputed_claims=[c for c in claims if c['status'] in ('DISPUTED','FALSE_OR_MISLEADING')],
                  primary_sources=[a['source_id'] for a in packet.get('source_assessments',[]) if a.get('primary_or_secondary')=='PRIMARY'],
                  secondary_sources=[a['source_id'] for a in packet.get('source_assessments',[]) if a.get('primary_or_secondary')=='SECONDARY'])
    passages={}
    for c in claims:
        for p in c['passages']:
            item=passages.setdefault(p['passage_id'],deepcopy(p))
            item['claim_ids']=sorted(set(item['claim_ids']+[c['claim_id']]))
    packet['evidence_passages']=list(passages.values())
    return packet
