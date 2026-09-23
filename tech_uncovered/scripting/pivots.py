"""Evidence-only editorial recommendations; never a generation authorization."""

def recommend_pivot(packet, plan, selected, outcome):
    if not packet or outcome.get('stop_reason')!='ANGLE_UNSUPPORTED':return None
    packet['angle_feasibility_status']='ANGLE_UNSUPPORTED'
    if not plan.get('comparison_required'):
        return documentation_pivot(packet,plan,selected,outcome)
    if packet.get('research_status')!='PARTIAL' or packet.get('comparison_supported'):return None
    angle_ids={q['requirement_id'] for q in plan.get('requirement_queue',[]) if q['category'].startswith('COMPARISON')}
    attempted=set(outcome.get('requirements_attempted',[]))
    if not angle_ids or not angle_ids<=attempted:return None
    if outcome.get('unused_search_budget',1)>0 and outcome.get('angle_unsupported_reason')!='REPEATED_NO_RELEVANT_EVIDENCE':return None
    identity=any(c.get('claim_type')=='IDENTITY_EVENT' and c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')
                 and c.get('evidence_link_method')=='STRUCTURED_DOCUMENTATION_OBSERVATION' for c in packet['claims'])
    claims=[c for c in packet['claims'] if c['status']=='VERIFIED' and c.get('materiality') in ('HIGH','CRITICAL')
            and c.get('evidence_link_method')=='STRUCTURED_DOCUMENTATION_OBSERVATION' and c.get('passages') and c.get('evidence_ids')]
    if not identity or len(claims)<3 or not packet.get('freshness_assessments',{}).get('EVERGREEN',{}).get('established'):return None
    topics=list(dict.fromkeys(t for c in claims for t in c['documented_topics']))
    recommendation={'status':'ANGLE_PIVOT_RECOMMENDED','original_angle':selected['idea']['proposed_angle'],
        'why_original_failed':packet.get('comparison_evidence',{}).get('rationale') or 'No verified alternative under a like-for-like criterion.',
        'recommended_angle':f"What the documentation establishes about {plan['canonical_topic']}: "+', '.join(topics)+'.',
        'verified_claim_ids_supporting_pivot':[c['claim_id'] for c in claims],
        'pivot_requires_new_research':False,'pivot_confidence':'HIGH_FOR_DOCUMENTED_SCOPE_ONLY',
        'freshness_mode':'EVERGREEN','requires_editorial_acceptance':True,
        'limitations':['Existing evidence can seed this narrower angle; script generation and all factual/editorial gates must still run.',
                      'No launch timing, independent performance or comparative claim is authorized.']}
    packet['angle_pivot']=recommendation
    return recommendation


def documentation_pivot(packet,plan,selected,outcome):
    """Reuse a bounded safe angle only when every positive clause has exact evidence."""
    if packet.get('research_status')!='PARTIAL':return None
    if outcome.get('angle_unsupported_reason')!='RESEARCH_ATTEMPTED_WITHOUT_SUFFICIENT_SUPPORT':return None
    required={q['requirement_id'] for q in plan.get('requirement_queue',[]) if q['category']=='TECHNICAL_MECHANISM'}
    if not required or not required<=set(outcome.get('requirements_attempted',[])):return None
    linked=[c for c in packet['claims'] if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')
            and c.get('evidence_link_method')=='STRUCTURED_DOCUMENTATION_OBSERVATION' and c.get('passages')]
    identity=[c for c in linked if c.get('claim_type')=='IDENTITY_AVAILABILITY']
    details=[c for c in linked if c.get('claim_type')=='TECHNICAL_DOCUMENTATION'
             and {'configurable reasoning effort','Responses API tool support'}<=set(c.get('documented_topics',[]))]
    if not identity or not details or not packet.get('freshness_assessments',{}).get('EVERGREEN',{}).get('established'):return None
    sources={s['source_id']:s for s in packet['source_records']}
    owners={sources[i].get('source_owner') for c in identity+details for i in c['evidence_ids']}
    if len(owners)!=1 or not next(iter(owners)):return None
    owner=next(iter(owners))
    safe=f"{owner}’s documentation lists {plan['canonical_topic']} as an API model with configurable reasoning effort and Responses-API tool support; what remains unproven is any specific workflow payoff."
    # A model's arbitrary safe-angle prose is never itself evidence.
    if packet.get('safe_angle')!=safe:return None
    pivot=dict(status='ANGLE_PIVOT_RECOMMENDED',original_angle=selected['idea']['proposed_angle'],
        why_original_failed='No dated release or concrete documented workflow outcome was established.',
        recommended_angle=safe,verified_claim_ids_supporting_pivot=[c['claim_id'] for c in details],
        pivot_requires_new_research=False,pivot_confidence='HIGH_FOR_DOCUMENTED_SCOPE_ONLY',
        freshness_mode='EVERGREEN',requires_editorial_acceptance=True,
        forbidden_claims=['LAUNCH_DATE','BREAKING_NEWS','FINALLY_HERE','SUPERIORITY','REALLY_GOOD',
                          'WORKFLOW_TRANSFORMATION','PRODUCTIVITY_IMPROVEMENT','RELIABILITY','BENCHMARK'],
        limitations=['Attributed documentation observations only; no workflow payoff or release timing.',
                    'Generation, independent fact checking and editorial gates must still pass.'])
    packet['angle_pivot']=pivot
    return pivot
