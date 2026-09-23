"""Deterministic research questions and bounded discovery; no asserted product facts."""
import re
from .models import stable_id


def query_key(text):
    aliases={'announced':'release','announcement':'release','released':'release','docs':'documentation'}
    return ' '.join(sorted({aliases.get(w,w) for w in re.findall(r'[a-z0-9]+',text.casefold())
                            if w not in {'the','a','an','and','or','for','of','what','which'}}))


def comparison_idea(idea):
    return any('comparison' in str(idea.get(k,'')).casefold() for k in ('transformation','proposed_angle'))


def prepare(plan,selected):
    idea=selected['idea'];resolution=plan.get('story_resolution') or {}
    subject=resolution.get('canonical_subject') or idea.get('canonical_subject') or idea['topic']
    domains=sorted({e['domain'] for e in resolution.get('evidence',[])
                    if e.get('source_authority_type')=='FIRST_PARTY' and e.get('domain')})
    scope=('site:'+domains[0]+' ') if domains else ''
    plan['requirements']=[r for r in plan['requirements'] if not r.get('generated_discovery_requirement')]
    reqs=plan['requirements'];queue=[]
    def add(category,text,terms,req=None):
        if req is None:
            req={'requirement_id':stable_id('requirement',text),'text':text,'generated_discovery_requirement':True}
            if not any(r['requirement_id']==req['requirement_id'] for r in reqs):reqs.append(req)
        queue.append({'requirement_id':req['requirement_id'],'category':category,'question':text,
                      'queries':[scope+subject+' '+terms,subject+' '+terms+' independent evidence'],
                      'status':'UNRESOLVED','material':True})
    identity=next((r for r in reqs if re.search(r'underlying subject|release|identity|event',r['text'],re.I)),None)
    if identity:add('IDENTITY_EVENT',f'Was {subject} officially announced or released?', 'official release announcement',identity)
    if comparison_idea(idea):
        add('PRIMARY_DOCUMENTATION',f'What primary documentation establishes {subject} capabilities, availability and constraints?', 'documentation API pricing availability capabilities')
        comp=next((r for r in reqs if re.search(r'compar|alternative',r['text'],re.I)),None)
        add('COMPARISON_ALTERNATIVE',f'What evidence identifies a relevant alternative to {subject} for the audience decision?', 'alternatives comparison documented trade-offs',comp)
        # Alternative discovery must not be limited to the original vendor's domain.
        queue[-1]['queries'][0]=subject+' alternatives comparison documented trade-offs'
        add('COMPARISON_CRITERION',f'What decision and like-for-like criterion can be supported for both {subject} and an evidence-selected alternative?', 'comparison same criterion limitations independent evidence')
        queue[-1]['queries']=[subject+' comparison same criterion limitations independent evidence',
                              subject+' comparison methodology comparable conditions documentation']
    for req in list(reqs):
        if any(q['requirement_id']==req['requirement_id'] for q in queue):continue
        category=next((cat for pattern,cat in [(r'pric|cost','PRICING'),(r'avail|access','AVAILABILITY'),
            (r'benchmark','BENCHMARK'),(r'safe|secur','SAFETY'),(r'limit|constraint','LIMITATION'),
            (r'capab','CAPABILITY')] if re.search(pattern,req['text'],re.I)),'TECHNICAL_MECHANISM')
        add(category,req['text'],category.lower().replace('_',' ')+' documentation',req)
    if not queue:add('IDENTITY_EVENT',f'Was {subject} officially announced or released?', 'official release announcement')
    plan.update(canonical_topic=subject,requirement_queue=queue,comparison_required=comparison_idea(idea))
    claims=[];seen={}
    for claim in plan['claims_to_verify']:
        if claim.get('origin_claim_ids')==[]:continue
        old=claim.get('original_text',claim['text']);key=query_key(old)
        if key in seen:
            seen[key]['origin_claim_ids'].append(claim['claim_id']);continue
        value=dict(claim,original_text=old,origin_claim_ids=claim.get('origin_claim_ids',[claim['claim_id']]),statement_type='RESEARCH_QUESTION')
        if 'validate the underlying subject' in old.casefold():value['text']=f'Was {subject} officially announced or released?'
        seen[key]=value;claims.append(value)
    questions={query_key(c['text']) for c in claims}
    for req in queue:
        if query_key(req['question']) not in questions:
            claims.append({'claim_id':stable_id('question',req['requirement_id']),'text':req['question'],
                'requirement_id':req['requirement_id'],'materiality':'CRITICAL','status':'UNVERIFIED',
                'statement_type':'RESEARCH_QUESTION','origin_claim_ids':[]})
            questions.add(query_key(req['question']))
    plan['claims_to_verify']=claims
    return queue


def next_query(requirement,attempt,packet,subject):
    if requirement['category']=='COMPARISON_CRITERION' and packet:
        comparison=packet.get('comparison_evidence',{})
        # Candidate names/criteria are usable for discovery only after passage grounding.
        if packet.get('comparison_candidate_grounded'):
            return f"{subject} {comparison['alternative']} {comparison['criterion']} official documentation same conditions"
    return requirement['queries'][min(attempt,len(requirement['queries'])-1)]
