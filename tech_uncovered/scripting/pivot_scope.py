"""Bounded entailment for documented specifications, with fail-closed diagnostics.

This is deliberately not general semantic inference. Unknown formulations remain
editorial review; they are not asserted to need research merely for being unknown.
"""
from copy import deepcopy
from decimal import Decimal
import re

FAILURES={'BROADER_THAN_EVIDENCE','NEW_UNSUPPORTED_CLAIM','FORBIDDEN_CATEGORY'}
PROPOSITION=dict(text='One proposition',claim_ids=['claim-id'],evidence_ids=['source-id'],passage_ids=['passage-id'],factual=True)
ANGLE_CONTRACT=dict(scope_contract_version=2,angle='Concise angle',audience_question='Audience question',
    payoff='Audience payoff',why_this_angle='Editorial reason',evidence_basis=['claim-id'],
    propositions=[dict(PROPOSITION,surface='angle')],do_not_say=[],required_nuance=[],visual_opportunities=[],
    refinement_status='REFINED',originality_status='REVIEW',originality_rationale='Evidence-only framing; competitor execution not assessed',
    forbidden_claim_self_check={'passed':True,'notes':'No forbidden factual assertions'},editorial_status='READY',
    required_research_assertions=[])
FORBIDDEN={
 'LAUNCH_DATE':r'\b(launched|released|announced|launch date)\b',
 'BREAKING_NEWS':r'\b(just launched|new today|breaking news|newly released)\b',
 'AGI':r'\b(agi|artificial general intelligence)\b',
 'SUPERIORITY':r'\b(best|most capable|superiority|superior|outperforms?|beats?|better than)\b',
 'BENCHMARK':r'\b(benchmarks?|benchmarking)\b',
 'COMPETITOR_COMPARISON':r'\b(competing models|competitors?|compared (?:with|to)|versus|vs\.?)\b',
 'RELIABILITY':r'\b(reliab\w*|guarantee\w*|autonomously|any computer)\b',
 'BROAD_AVAILABILITY':r'\b(broad availability|broadly available|universal availability|universally available|generally available|available to (?:everyone|anyone))\b',
 'SAFETY_CONCLUSION':r'\b(safer|safest|safe to|secure|risk.free|safety proven)\b'}
EDITORIAL={"here is what the docs actually say","here's what the docs actually say","there is a catch",
           "there's a catch","the interesting part is the trade-off","what do the docs actually say"}


def norm(text):
    return re.sub(r'\s+',' ',text.casefold().replace('’',"'").strip().rstrip('.?!'))


def number(text):
    text=text.lower().replace(',','').strip()
    match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(million|thousand|m|k)?',text)
    return Decimal(match[1])*{'million':1000000,'m':1000000,'thousand':1000,'k':1000,None:1}[match[2]] if match else None


def compact_bundle(packet,config):
    acceptance=packet['pivot_acceptance'];claims=[];passages={}
    for c in packet['claims']:
        if c['claim_id'] not in acceptance['allowed_claim_scope']:continue
        claims.append({k:deepcopy(c.get(k,[])) for k in ('claim_id','status','supported_wording','limitations','evidence_ids')})
        claims[-1]['passage_ids']=[p['passage_id'] for p in c['passages'] if p['relation']=='SUPPORTS']
        for p in c['passages']:
            if p['relation']!='SUPPORTS':continue
            entry=passages.setdefault(p['passage_id'],dict(passage_id=p['passage_id'],source_id=p['source_id'],
                text=p['quote'],claim_ids=[]))
            if c['claim_id'] not in entry['claim_ids']:entry['claim_ids'].append(c['claim_id'])
    return dict(canonical_subject=packet['topic'],accepted_pivot=acceptance['accepted_angle'],
        allowed_claim_ids=list(acceptance['allowed_claim_scope']),claims=claims,passages=list(passages.values()),
        forbidden_categories=acceptance['forbidden_claims'],format_style=dict(
            word_bounds=[config['script_word_min'],config['script_word_max']],duration_bounds=[config['duration_min_seconds'],config['duration_max_seconds']],
            structure='0–3s hook; 3–10s setup; 10–40s explanation; 40–52s payoff; optional CTA',
            style='Concise, intelligent, conversational, evidence-attributed evergreen documentation explainer. No hype.',
            quality_threshold=config['quality_threshold']))


def _body(text,packet):
    """Strip only attribution/subject phrases, not qualifiers or unsupported facts."""
    s=norm(text)
    subject=norm(packet['topic']);aliases=[subject,subject.split()[-1],'the model','the model page','the documentation','the docs']
    owners={norm(x.get('source_owner','')) for x in packet.get('source_records',[]) if x.get('source_owner')}
    # Publisher names occur in the supported wording; no invented name may be stripped.
    owners.update(re.findall(r'([A-Z][A-Za-z]+)[’\']s (?:documentation|model page|developer)', ' '.join(c['supported_wording'] for c in packet['claims'])))
    owners={norm(x) for x in owners}
    leads=['according to the model page,','according to the documentation,']
    leads += [owner+"'s "+form for owner in owners for form in ('model page lists','documentation lists','documentation says')]
    leads += [owner+' '+verb for owner in owners for verb in ('documents','lists','says','reports')]
    leads += [x+' '+verb for x in ('the model page','the documentation','the docs') for verb in ('lists','says','documents')]
    attributed=False
    for lead in sorted(leads,key=len,reverse=True):
        if s.startswith(lead+' '):s=s[len(lead):].strip();attributed=True;break
    for alias in sorted(aliases,key=len,reverse=True):
        if s.startswith(alias+' '):s=s[len(alias):].strip();break
    for alias in sorted(aliases,key=len,reverse=True):s=s.replace(' for '+alias+' ',' ')
    return s,attributed


def entailed(text,claims,passages,packet):
    normalized=norm(text)
    matching=[c for c in claims if normalized==norm(c['supported_wording'])]
    if matching and any({p['passage_id'] for p in c['passages'] if p['relation']=='SUPPORTS'}<={p['passage_id'] for p in passages} for c in matching):
        return 'SUPPORTED_EXACT','Matches the authorized scoped wording with its supporting passages.'
    body,attributed=_body(text,packet);evidence=' '.join(p['quote'] for p in passages)
    # Complete proposition grammars prevent an added clause from borrowing support.
    if re.fullmatch(r'computer[ -]use (?:is )?(?:listed as |as )?supported (?:through|in|with|when using|via) the responses api',body):
        if re.search(r'Computer use Supported',evidence,re.I) and re.search(r'Tools supported by this model when using the Responses API',evidence,re.I):
            return 'SUPPORTED_PARAPHRASE','Tool support and Responses API scope are both explicitly documented; no performance inference.'
    if re.fullmatch(r'fine-tuning (?:is )?(?:listed as |as )?(?:unsupported|not supported)',body) and (attributed or 'listed' in body):
        if re.search(r'Fine-tuning Not supported',evidence,re.I):return 'SUPPORTED_PARAPHRASE','Preserves the documented fine-tuning restriction, without generalizing to customization.'
    numeric=r'(\d[\d,]*(?:\.\d+)?\s*(?:million|thousand|m|k)?)'
    m=re.fullmatch(r'(?:a |an )?'+numeric+r'(?:[ -]token)? context window',body)
    if m and attributed:
        found=re.search(r'([\d,]+) context window',evidence,re.I)
        if found and number(m[1])==number(found[1]):return 'SUPPORTED_PARAPHRASE','Exact numeric equality for the documented context window.'
    m=re.fullmatch(r'(?:a maximum of |up to )?'+numeric+r'(?: maximum|max)? output tokens',body)
    if m and attributed:
        found=re.search(r'([\d,]+) max output tokens',evidence,re.I)
        if found and number(m[1])==number(found[1]):return 'SUPPORTED_PARAPHRASE','Exact numeric equality for the documented output limit.'
    m=re.fullmatch(r'\$([\d.]+) per (?:million|1m) (input|output) tokens(?: as (?:the )?(?:listed )?base (?:price|rate))?',body)
    if m and attributed:
        found=re.search(r'\b'+m[2]+r' \$([\d.]+)',evidence,re.I)
        if found and Decimal(m[1])==Decimal(found[1]) and 'Per 1M tokens' in evidence:
            # Pricing scope is base table rates; modifiers must remain acknowledged.
            if 'base' in body:return 'SUPPORTED_PARAPHRASE','Exact documented base-rate equality; does not imply universal billing.'
    if re.fullmatch(r'(?:audio and video|video and audio) (?:are )?(?:listed as )?(?:unsupported|not supported)',body) and (attributed or 'listed' in body):
        if 'Audio Not supported' in evidence and 'Video Not supported' in evidence:return 'SUPPORTED_PARAPHRASE','Preserves the model modality restrictions.'
    return 'BROADER_THAN_EVIDENCE','Entailment is not established by the bounded documentation rules; rephrase within mapped evidence or obtain independent semantic review.'


def classify(proposition,packet):
    p=deepcopy(proposition);p.setdefault('text','');p.setdefault('factual',True)
    p.setdefault('claim_ids',[]);p.setdefault('evidence_ids',[]);p.setdefault('passage_ids',[])
    def finish(category,reason):p.update(classification=category,reason=reason);return p
    if not isinstance(p['text'],str):return finish('NEW_UNSUPPORTED_CLAIM','Proposition text must be a string.')
    from .scope_language import polarity, entirely_cautionary, editorial
    parts=re.split(r'(?<=[.!?])\s+',p['text'].strip())
    if len(parts)>1:
        units=[]
        for text in parts:
            child=dict(p,text=text)
            if editorial(text,EDITORIAL):child['factual']=False
            units.append(classify(child,packet))
        p['atomic_units']=units
        p['polarity_analysis']=[x for u in units for x in u.get('polarity_analysis',[])]
        bad=[u for u in units if u['classification'] in FAILURES]
        return finish(bad[0]['classification'] if bad else 'SUPPORTED_COMPOSITE_PARAPHRASE',
                      'Every sentence is independently classified with parent-authorized mappings.')
    p['polarity_analysis']=polarity(p['text'],FORBIDDEN)
    # Complete framing labels/questions assert no product capability.
    subject=re.escape(norm(packet['topic']))
    owners=[re.escape(norm(s['source_owner'])) for s in packet.get('source_records',[]) if s.get('source_owner')]
    labels=[subject+r': what the docs actually list',r'what '+subject+r' can use']
    labels += [r'what '+owner+r' actually documents' for owner in owners]
    labels += [owner+r' documentation: '+subject for owner in owners]
    if any(re.fullmatch(pattern,norm(p['text'])) for pattern in labels):
        return finish('NONFACTUAL_EDITORIAL','Subject-bound documentation framing label; no capability assertion.')
    positive=[item for item in p['polarity_analysis'] if item['polarity']=='ASSERTION']
    # Branch on editorial intent before requiring evidence, while independently
    # checking the construction for disguised assertions and positive hard gates.
    if not positive and entirely_cautionary(p['text']):
        return finish('NONFACTUAL_EDITORIAL','Caution against an unsupported inference; no positive product claim is asserted.')
    if p['factual'] is False and editorial(p['text'],EDITORIAL):
        for item in p['polarity_analysis']:
            item.update(polarity='NONFACTUAL_MENTION',reason='Concept mentioned in editorial guidance, without an asserted product property.')
        return finish('NONFACTUAL_EDITORIAL','Editorial treatment or reader guidance, without a factual product assertion; evidence mappings are not required.')
    if positive and not (isinstance(p.get('claim_ids'),list) and len(p['claim_ids'])>1):
        return finish('FORBIDDEN_CATEGORY',positive[0]['category']+' is positively asserted, not negated or cautioned against.')
    claims={c['claim_id']:c for c in packet['claims'] if c['claim_id'] in packet.get('pivot_acceptance',{}).get('allowed_claim_scope',{c['claim_id']:{} for c in packet['claims'] if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')})}
    if any(not isinstance(p[k],list) or any(not isinstance(i,str) for i in p[k]) for k in ('claim_ids','evidence_ids','passage_ids')):
        return finish('NEW_UNSUPPORTED_CLAIM','Mappings must be explicit arrays of IDs.')
    if not p['claim_ids'] or not set(p['claim_ids'])<=set(claims):return finish('NEW_UNSUPPORTED_CLAIM','A factual proposition needs authorized claim IDs; an editorial label cannot exempt factual wording.')
    chosen=[claims[cid] for cid in p['claim_ids']]
    if any(c['status'] not in ('VERIFIED','PARTIALLY_VERIFIED') for c in chosen):return finish('NEW_UNSUPPORTED_CLAIM','Mapped claim is not authorized as supported.')
    available={e['passage_id']:e for c in chosen for e in c['passages'] if e['relation']=='SUPPORTS'}
    sources={sid for c in chosen for sid in c['evidence_ids']}
    if not p['passage_ids'] or not p['evidence_ids'] or not set(p['passage_ids'])<=available.keys() or not set(p['evidence_ids'])<=sources:
        return finish('NEW_UNSUPPORTED_CLAIM','Evidence and passage IDs must belong to the mapped claims.')
    linked=[available[e] for e in p['passage_ids']]
    if any(e['source_id'] not in p['evidence_ids'] for e in linked) or any(not any(e['passage_id'] in p['passage_ids'] and e['source_id'] in p['evidence_ids'] for e in c['passages']) for c in chosen):
        return finish('NEW_UNSUPPORTED_CLAIM','Each mapped claim requires a matching source and passage tuple.')
    from .scope_composition import concise_support
    direct=[]
    for claim in chosen:
        own=[e for e in linked if e['passage_id'] in {x['passage_id'] for x in claim['passages']}]
        supported=concise_support(p['text'],claim,own,packet)
        if supported:direct.append((claim,supported))
    if direct and not positive:
        p['atomic_units']=[dict(text=p['text'],classification='SUPPORTED_PARAPHRASE',
            claim_ids=[c['claim_id']],inherited_claim_ids=[c['claim_id']],
            evidence_ids=sorted({e['source_id'] for e in es}),passage_ids=[e['passage_id'] for e in es],
            reason='Bounded documentation paraphrase supported by parent-cited passages.') for c,es in direct]
        return finish('SUPPORTED_PARAPHRASE','Authorized documentation observation.')
    category,reason=entailed(p['text'],chosen,linked,packet)
    if not positive and category in ('SUPPORTED_EXACT','SUPPORTED_PARAPHRASE'):return finish(category,reason)
    from .scope_language import atomic_texts, category_support
    units=[]
    for text in atomic_texts(p['text']):
        forbidden_units=[item for item in polarity(text,FORBIDDEN) if item['polarity']=='ASSERTION']
        if forbidden_units:
            units.append(dict(text=text,claim_ids=[],classification='FORBIDDEN_CATEGORY',reason=forbidden_units[0]['category']+' is positively asserted.'))
            continue
        supporters=[];supporting_passages={}
        for claim in chosen:
            own=[e for e in linked if e['passage_id'] in {x['passage_id'] for x in claim['passages']} and e['source_id'] in claim['evidence_ids']]
            cat,_=entailed(text,[claim],own,packet)
            from .scope_composition import support, concise_support
            derived=support(text,p['text'],claim,own,packet) or concise_support(text,claim,own,packet)
            if category_support(text,own) or cat in ('SUPPORTED_EXACT','SUPPORTED_PARAPHRASE'):
                derived=own
            if derived:
                supporters.append(claim['claim_id'])
                supporting_passages.update({e['passage_id']:e for e in derived})
        units.append(dict(text=text,claim_ids=supporters,
            inherited_claim_ids=supporters,
            evidence_ids=sorted({e['source_id'] for e in supporting_passages.values()}),
            passage_ids=sorted(supporting_passages),
            classification='SUPPORTED_PARAPHRASE' if supporters else 'BROADER_THAN_EVIDENCE',
            reason='Category or scoped proposition is covered by the mapped claim’s cited structured fields; no evaluative inference.' if supporters else 'This atomic unit is not supported by any mapped claim and its cited passages.'))
    p['atomic_units']=units
    if positive:return finish('FORBIDDEN_CATEGORY',positive[0]['category']+' is positively asserted; see atomic_units.')
    if units and all(u['claim_ids'] for u in units):
        return finish('SUPPORTED_COMPOSITE_PARAPHRASE' if len(units)>1 else 'SUPPORTED_PARAPHRASE',
                      'Every atomic component is supported by the union of authorized claim-relative evidence.')
    return finish('BROADER_THAN_EVIDENCE','At least one atomic component lacks support; see atomic_units for the exact rejected text.')



def validate_candidate(candidate,packet,stage,candidate_id):
    props=candidate.get('propositions',[]) if isinstance(candidate,dict) else []
    results=[classify(p,packet) for p in props if isinstance(p,dict)]
    # Exact coverage joins generator surface text to assertions; it is NOT evidence matching.
    if stage=='angle_refinement':
        for surface in ('angle','payoff'):
            text=candidate.get(surface,'')
            covering=[p for p in props if isinstance(p,dict) and p.get('surface')==surface]
            if not text or ' '.join(p.get('text','') for p in covering)!=text:
                results.append(dict(text=text,factual=True,claim_ids=[],evidence_ids=[],passage_ids=[],surface=surface,
                    classification='BROADER_THAN_EVIDENCE',reason='Every displayed angle/payoff span must be represented in propositions, in order.'))
    if stage=='script_outline':
        for index,beat in enumerate(candidate.get('beats',[])):
            text=beat.get('purpose','');covering=[p for p in props if isinstance(p,dict) and p.get('surface')==str(index)]
            if not text or ' '.join(' '.join(p.get('text','') for p in covering).split())!=' '.join(text.split()):
                results.append(dict(text=text,factual=True,claim_ids=[],evidence_ids=[],passage_ids=[],classification='BROADER_THAN_EVIDENCE',reason='Outline purpose lacks complete proposition coverage.'))
    if not props:results.append(dict(text=str(candidate.get('angle',candidate)),factual=True,claim_ids=[],evidence_ids=[],passage_ids=[],classification='BROADER_THAN_EVIDENCE',reason='Explicit factual/editorial propositions missing.'))
    if candidate.get('forbidden_claim_self_check',{}).get('passed') is False:
        results.append(dict(text=candidate['forbidden_claim_self_check'].get('notes',''),factual=False,claim_ids=[],evidence_ids=[],passage_ids=[],classification='BROADER_THAN_EVIDENCE',reason='Generator self-check requests editorial correction.'))
    for text in candidate.get('required_research_assertions',[]):
        results.append(dict(text=str(text),factual=True,claim_ids=[],evidence_ids=[],passage_ids=[],classification='NEW_UNSUPPORTED_CLAIM',reason='Generator explicitly identifies a new material fact requiring research.'))
    failures=[r for r in results if r['classification'] in FAILURES]
    need_research=any(r['classification']=='NEW_UNSUPPORTED_CLAIM' for r in failures)
    return dict(stage=stage,candidate_id=candidate_id,propositions=results,result='FAIL' if failures else 'PASS',
        failure_categories=sorted({r['classification'] for r in failures}),
        rejected_spans=[{'text':u['text'],'reason':u['reason']} for r in failures for u in (
            [a for a in r.get('atomic_units',[]) if a['classification'] in FAILURES] or [r])],
        next_status='RESEARCH_REQUIRED' if need_research else 'EDITORIAL_REVIEW' if failures or candidate.get('editorial_status')=='EDITORIAL_REVIEW' else 'CONTINUE')


def validated_angle(candidate,report):
    """Canonicalize legacy summary IDs from the already validated v2 propositions."""
    if report['result']!='PASS' or report['next_status']!='CONTINUE':raise ValueError('Angle scope has not passed')
    angle=deepcopy(candidate)
    if angle.get('scope_contract_version')==2:
        ids={cid for p in report['propositions'] if p['classification'] in ('SUPPORTED_EXACT','SUPPORTED_PARAPHRASE','SUPPORTED_COMPOSITE_PARAPHRASE') for cid in p['claim_ids']}
        if ids:angle['evidence_basis']=sorted(ids)
    return angle
