"""Cheap story identity check; never a substitute for claim verification."""
import json
import re
import math
from copy import deepcopy
from urllib.parse import urlsplit
from .sources import canonical_url, topic_relevance

RESOLUTION_EXAMPLE={
    'canonical_subject':'','named_entities':[], 'alleged_event':'','event_date_if_known':'',
    'identifiers':{'products':[],'companies':[],'people':[]},'resolvability_score':0.0,
    'ambiguity_flags':[],'suggested_queries':[],'status':'UNRESOLVED',
    'evidence':[{'url':'','quote':'','source_type':'OTHER','independent_of_competitor':False,
                 'indicates_event':False,'contradicts_event':False,'authority_reason':''}]}
GENERIC={'ai','technology','software','computing','unknown','artificial intelligence','new ai'}


def specific(value):
    return isinstance(value,str) and len(value.strip())>=3 and value.strip().lower() not in GENERIC


def assess_researchability(selected):
    idea=selected['idea'];contexts=idea.get('story_context',[]);flags=[]
    subjects=[c.get('canonical_subject') for c in contexts if specific(c.get('canonical_subject'))]
    names=sorted({v for c in contexts for k in ('entities','products_models','companies','people') for v in c.get(k,[]) if specific(v)})
    events=[c.get('core_event') or c.get('what_changed') for c in contexts if c.get('core_event') or c.get('what_changed')]
    if not subjects:flags.append('NO_CANONICAL_SUBJECT')
    if not names:flags.append('NO_CONTEXT_IDENTIFIERS')
    if not events:flags.append('NO_IDENTIFIABLE_EVENT')
    limited='CONTEXT_LIMITED' in idea.get('risk_flags',[]) or any('CONTEXT_LIMITED' in c.get('flags',[]) for c in contexts)
    if limited:flags.append('CONTEXT_LIMITED')
    confidence=max([0]+[float(c.get('confidence') or 0) for c in contexts])
    # Title hints are weaker than supplied story context; never establish existence.
    titles=' '.join(r['title'] for r in selected['competitor_references'])
    title_hint=bool(re.search(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}[’']s",titles))
    score=25*bool(subjects)+25*bool(names)+25*bool(events)+10*(len(idea['source_video_ids'])>1)+10*min(1,max(0,confidence))+5*(not limited)
    if not names and title_hint:score+=5;flags.append('TITLE_ONLY_IDENTIFIER_HINT')
    return {'researchability_score':round(score,2),'unresolved_flags':flags,'context_status':'CONTEXT_LIMITED' if limited else 'CONTEXT_AVAILABLE'}


def validate_resolution(raw,sources,selected,threshold=70,*,discoveries=None,authorities=None,score_threshold=70):
    """Resolve identity from authenticated discovery/fetch provenance, not generated quotes.

    Legacy raw evidence alone does not prove that the search provider returned a URL.
    Sources and discovery records must come from the provider boundary, not model JSON.
    """
    from .models import stable_id
    result=deepcopy(raw);credible=[];records=[];owners=set();warnings=[]
    generated_flags={'NO_INDEPENDENT_EVENT_EVIDENCE','MISSING_SPECIFIC_SUBJECT_ENTITY_OR_EVENT'}
    flags=[f for f in raw.get('ambiguity_flags',[]) if f not in generated_flags]
    registry=authorities if authorities is not None else {'openai.com':'OpenAI'}
    refs={canonical_url(r['url']) for r in selected['competitor_references']}
    hits={canonical_url(h['url']):h for h in discoveries or []}
    fetched={canonical_url(s['url']):s for s in sources if s.get('text')}
    entity_ok=any(specific(n) for n in raw.get('named_entities',[]))
    subject_ok=specific(raw.get('canonical_subject')) and entity_ok
    event_ok=specific(raw.get('alleged_event'))
    contradictions=0;identity_evidence=0;seen=set()
    for evidence in raw.get('evidence',[]):
        url=canonical_url(evidence.get('url',''));host=urlsplit(url).hostname or ''
        if not host or url in seen:continue
        seen.add(url);source=fetched.get(url);hit=hits.get(url)
        from .authority import classify
        classification=classify(url,registry,source)
        owner=classification['source_owner'];authority=classification['authority_type']
        if authority=='FIRST_PARTY' and not any(n.casefold() in owner.casefold() for n in raw.get('identifiers',{}).get('companies',[]) if specific(n)):
            authority='UNKNOWN'
        competitor=url in refs or host in ('youtu.be','youtube.com') or host.endswith('.youtube.com')
        if competitor:authority='COMPETITOR'
        record={'evidence_id':stable_id('resolution-source',url),'url':url,'domain':host,
                'source_owner':owner or host,'source_authority_type':authority,
                'source_role':authority,'acquisition_state':'FETCHED' if source else 'DISCOVERED' if hit else None,
                'independent_of_competitor':evidence.get('independent_of_competitor') is True,
                'indicates_event':evidence.get('indicates_event') is True,
                'contradicts_event':evidence.get('contradicts_event') is True or evidence.get('relation')=='CONTRADICTS',
                'discovery_confirmed':bool(hit or source),
                'discovered_via_query':hit.get('discovered_via_query') if hit else None,
                'result_title':hit.get('result_title') if hit else None,
                'result_snippet':hit.get('result_snippet') if hit else None,
                'fetched':bool(source),'verified_passage_count':0,'accepted':False}
        if source:
            record['research_source_id']=source['source_id']
            quote=' '.join(evidence.get('quote','').split())
            copied_title=any(' '.join(r['title'].lower().split()) in quote.lower() for r in selected['competitor_references'])
            if len(quote)>=30 and quote in ' '.join(source['text'].split()) and not copied_title:
                record.update(acquisition_state='VERIFIED_PASSAGE',quote=quote,verified_passage_count=1)
            elif quote:warnings.append('UNVERIFIED_MODEL_QUOTE_DROPPED')
        elif evidence.get('quote'):warnings.append('UNFETCHED_MODEL_QUOTE_DROPPED')
        if not hit and not source:warnings.append('LEGACY_DISCOVERY_PROVENANCE_UNAVAILABLE')
        # Title/snippet are tool-returned only; URL path may identify a product page.
        identity_text=' '.join([url, str(record['result_title'] or ''),str(record['result_snippet'] or ''),
                               source.get('title','') if source else '']).casefold()
        norm=lambda x:re.sub(r'[^a-z0-9]+',' ',x.casefold()).strip()
        identifiers=raw.get('identifiers',{}).get('products') or raw.get('named_entities',[])
        matched=any(specific(n) and norm(n) in norm(identity_text) for n in identifiers)
        if source and not matched:
            matched=topic_relevance(source,raw)>=threshold or (not event_ok and any(
                specific(n) and norm(n) in norm(source['text']) for n in identifiers))
        independent=evidence.get('independent_of_competitor') is True
        accepted=bool((hit or source) and not competitor and independent and matched and authority in ('FIRST_PARTY','REPUTABLE_SECONDARY'))
        if accepted:
            identity_evidence+=1
            contradictory=evidence.get('contradicts_event') is True or evidence.get('relation')=='CONTRADICTS'
            contradictions+=int(contradictory)
            if evidence.get('indicates_event') is True and not contradictory:
                credible.append(record['evidence_id']);owners.add(record['source_owner']);record['accepted']=True
        records.append(record)
    score=raw.get('resolvability_score',0)
    valid_score=isinstance(score,(int,float)) and not isinstance(score,bool) and math.isfinite(score) and 0<=score<=100
    normalized=score*100 if valid_score and 0<=score<=1 else score if valid_score else 0
    contradictions+=sum('CONTRADICT' in str(f).upper() for f in flags)
    passes=subject_ok and event_ok and credible and normalized>=score_threshold and not contradictions and not flags
    status='RESOLVED' if passes else 'PARTIALLY_RESOLVED' if subject_ok and identity_evidence and not contradictions else 'UNRESOLVED'
    reason=('Specific subject and event anchored to credible non-competitor discovery/fetch evidence; full claims remain unverified.' if passes else
            'Contradictory evidence blocks resolution.' if contradictions else
            'Subject identified, but event, confidence, or ambiguity requires further resolution.' if status=='PARTIALLY_RESOLVED' else
            'No adequate credible evidence of a specific subject/event identity.')
    result.update(status=status,evidence=records,credible_source_ids=sorted(set(credible)),
                  independent_owner_count=len(owners),warnings=sorted(set(warnings)),decision_reason=reason,
                  ambiguity_flags=flags,normalized_resolvability_score=normalized,
                  decision_inputs={'canonical_subject':raw.get('canonical_subject'),'alleged_event':raw.get('alleged_event'),
                    'resolvability_score':normalized,'credible_non_competitor_sources':len(set(credible)),
                    'independent_owner_count':len(owners),'contradiction_count':contradictions})
    return result


def transient_fetch_error(exc):
    from urllib.error import HTTPError
    return isinstance(exc,(TimeoutError,ConnectionError)) or (isinstance(exc,HTTPError) and exc.code in (408,429,500,502,503,504)) or bool(re.search(r'HTTP status (408|429|500|502|503|504)\b',str(exc)))


class StoryResolutionGate:
    name,version='bounded-story-resolution','2'
    def resolve(self,selected,provider,budget,config):
        start=budget.clock();old=budget.config
        cap=min(.08,config.get('preflight_max_cost_usd',.08),config['max_model_cost_usd'])
        local=dict(config,max_model_cost_usd=cap,max_research_seconds=min(45,config.get('preflight_max_seconds',45),config['max_research_seconds']),
                   max_output_tokens=1200,max_attempts=1)
        budget.config=local;sources=[];raw=deepcopy(RESOLUTION_EXAMPLE);failures=[];hits=[]
        try:
            budget.check_time()
            raw,hits=provider.resolve_story(selected,local)
            budget.check_time()
            seen=set()
            for hit in hits:
                url=canonical_url(hit['url'])
                if url in seen:continue
                if len(seen)>=min(2,config['max_sources']):break
                seen.add(url)
                for attempt in range(2):
                    budget.check_time()
                    try:
                        source=provider.fetch(url).to_dict()
                        source.update(canonical_url=canonical_url(source['url']),retrieved_url=source['url']);sources.append(source);break
                    except Exception as exc:
                        from .costs import LimitReached
                        if isinstance(exc,LimitReached):raise
                        failures.append({'stage':'story_resolution_fetch','url':url,'error':type(exc).__name__,
                                         'attempt':attempt+1,'transient':transient_fetch_error(exc)})
                        host=urlsplit(url).hostname or ''
                        registry=config.get('resolution_authorities',{'openai.com':'OpenAI'})
                        official=any(host==d or host.endswith('.'+d) for d in registry)
                        if attempt or not official or not transient_fetch_error(exc):break
            budget.check_time()
            result=validate_resolution(raw,sources,selected,config.get('source_topic_relevance_threshold',70),
                discoveries=hits,authorities=config.get('resolution_authorities'),score_threshold=config.get('resolution_score_threshold',70))
        except Exception as exc:
            result=validate_resolution(raw,sources,selected,discoveries=hits,authorities=config.get('resolution_authorities'))
            result['warnings']=sorted(set(result['warnings']+['PREFLIGHT_PROVIDER_OR_BUDGET_FAILURE']))
            if not hits and not sources:
                result['status']='UNRESOLVED'
                result['decision_reason']='Preflight provider/budget failure before evidence acquisition; do not start full research.'
            failures.append({'stage':'story_resolution','error':type(exc).__name__})
        finally:budget.config=old
        if any(f['stage']=='story_resolution_fetch' for f in failures):
            result['warnings']=sorted(set(result['warnings']+['SOURCE_FETCH_PARTIAL_FAILURE']))
        result['elapsed_seconds']=budget.clock()-start;result['failures']=failures
        return result,sources
