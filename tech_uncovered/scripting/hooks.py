import math
HOOK_WEIGHTS={'Clarity':.20,'Specificity':.15,'Curiosity':.15,'Stakes':.10,'Novelty':.10,'FactualSafety':.20,'Brevity':.10}


def mapping_errors(item,packet):
    if item.get('factual') is False and packet.get('pivot_acceptance'):
        from .pivot_scope import classify
        p=classify({'text':item.get('text',''),'factual':False,'claim_ids':item.get('claim_ids',[]),'evidence_ids':item.get('source_ids',[]),'passage_ids':item.get('evidence_passage_ids',[])},packet)
        if p['classification']=='NONFACTUAL_EDITORIAL':return []
    claims={c['claim_id']:c for c in packet['claims']};errors=[]
    ids=item.get('claim_ids',[])
    if not ids:errors.append('MISSING_CLAIM_MAPPING')
    for cid in ids:
        c=claims.get(cid)
        if not c or c['status'] not in ('VERIFIED','PARTIALLY_VERIFIED'):errors.append('UNSUPPORTED_CLAIM:'+cid);continue
        passages={p['passage_id'] for p in c['passages'] if p['relation']=='SUPPORTS'}
        if not set(item.get('source_ids',[])) & set(c['evidence_ids']):errors.append('MISSING_SOURCE:'+cid)
        if not set(item.get('evidence_passage_ids',[])) & passages:errors.append('MISSING_PASSAGE:'+cid)
    known_sources={s['source_id'] for s in packet['source_records']}
    known_passages={p['passage_id'] for c in packet['claims'] for p in c['passages']}
    if not set(item.get('source_ids',[]))<=known_sources:errors.append('UNKNOWN_SOURCE')
    if not set(item.get('evidence_passage_ids',[]))<=known_passages:errors.append('UNKNOWN_PASSAGE')
    return errors


def score_hooks(hooks,packet):
    if len(hooks)!=5 or len({h['hook_id'] for h in hooks})!=5:raise ValueError('Exactly five distinct hooks required')
    for h in hooks:
        scores=h['scores']
        if set(scores)!=set(HOOK_WEIGHTS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=100 for v in scores.values()):raise ValueError('Invalid hook component score')
        errors=mapping_errors(h,packet)
        if h.get('scope_eligible') is False:errors.append('HOOK_SCOPE_REJECTED')
        if scores['FactualSafety']<90:errors.append('FACTUAL_SAFETY_BELOW_THRESHOLD')
        if any(phrase in h['text'].lower() for phrase in ('changes everything',"you won’t believe","you won't believe")):errors.append('UNSUPPORTED_HYPE')
        h['eligibility_reasons']=errors;h['eligible']=not errors
        h['score']=round(sum(scores[k]*w for k,w in HOOK_WEIGHTS.items()),3)
    eligible=sorted([h for h in hooks if h['eligible']],key=lambda h:(-h['score'],h['hook_id']))
    if not eligible:raise ValueError('No evidence-safe hook')
    return eligible[0]
