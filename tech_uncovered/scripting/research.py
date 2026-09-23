from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit
from .claims import validate_packet
from .pivots import recommend_pivot
from .costs import LimitReached, ProviderFailure
from .sources import priority, canonical_url, topic_relevance
from .models import stable_id
from .requirements import prepare, next_query, query_key
from .source_selection import rank_results,score_result


def collect(provider,synthesizer,plan,selected,budget,initial_sources=None):
    queue=prepare(plan,selected)
    sources=[];seen=set();failures=[];packet=None;searches=0;excluded=[];audit=[]
    attempts=Counter();query_keys=set();resolved=set();empty=0;last_synth_count=-1
    fetches=len(initial_sources or []);resolution=plan.get('story_resolution')
    threshold=budget.config.get('source_topic_relevance_threshold',70)
    limit=plan['max_search_calls'];per_requirement=plan.get('max_searches_per_requirement',2)
    if not isinstance(per_requirement,int) or per_requirement<1:raise ValueError('max_searches_per_requirement must be positive')
    angle_reason=None;stop='SEARCH_LIMIT';unsupported_reason=None
    subjects=[plan['canonical_topic']]+(resolution or {}).get('identifiers',{}).get('products',[])
    current_requirement=queue[0]
    def accept(source):
        url=source['url'];host=urlsplit(url).hostname or ''
        if host in ('youtube.com','www.youtube.com','youtu.be') or host.endswith('.youtube.com'):
            excluded.append({'url':url,'reason':'COMPETITOR_METADATA'});return False
        if source.get('acquisition_state')=='DISCOVERED' or not source.get('text'):
            excluded.append({'url':url,'reason':'UNFETCHED_DISCOVERY'});return False
        scored=score_result({'url':url},current_requirement,subjects,budget.config,source=source,now=plan['planned_at'])
        source.update({k:scored[k] for k in ('source_owner','authority_type','selection_components','selection_score','selection_warnings','eligible_for_primary_identity','exact_entity_match','document_type')})
        if scored['selection_rejection']:
            excluded.append({'url':url,'reason':scored['selection_rejection']});return False
        source.update(canonical_url=canonical_url(url),retrieved_url=source.get('retrieved_url') or url)
        relevance=topic_relevance(source,resolution)
        if packet and packet.get('comparison_candidate_grounded'):
            alt=packet['comparison_evidence']['alternative']
            alt_resolution={'named_entities':[alt],'identifiers':{'products':[alt]},'alleged_event':packet['comparison_evidence']['criterion']}
            relevance=max(relevance,topic_relevance(source,alt_resolution))
        source['source_topic_relevance']=relevance
        if relevance<threshold:
            excluded.append({'url':url,'reason':'OFF_TOPIC','source_topic_relevance':relevance});return False
        source['source_priority']=priority(source);sources.append(source);return True
    def synthesize():
        nonlocal packet,resolved,angle_reason,last_synth_count
        raw=synthesizer.synthesize(plan,sources,selected)
        packet=validate_packet(raw,sources,plan,selected);last_synth_count=len(sources)
        angle_reason=raw.get('early_stop_reason')
        resolved=set(packet.get('resolved_requirement_ids',[]))
        if angle_reason in ('ANGLE_UNSUPPORTED','ENTITY_UNCORROBORATED') and packet['research_status']!='CONTRADICTED':
            if packet['research_status']=='SUFFICIENT':packet['research_status']='PARTIAL'
            packet['remaining_questions_material']=True
        states={r['requirement_id']:r['status'] for r in packet.get('requirement_statuses',[])}
        for q in queue:q['status']=states.get(q['requirement_id'],'UNRESOLVED')
        # A model suggestion is not an execution-loop stop instruction.
        if packet.get('early_stop_reason')=='ANGLE_UNSUPPORTED':packet['early_stop_reason']=''
    def outcome(reason):
        angle_ids={q['requirement_id'] for q in queue if q['category'].startswith('COMPARISON')}
        return {'stop_reason':reason,'logical_search_calls':searches,'failures':failures,'excluded_sources':excluded,
            'research_searches':audit,'searches_by_requirement':dict(attempts),
            'requirements_attempted':sorted(attempts),'requirements_resolved':sorted(resolved),
            'requirements_unresolved':[q['requirement_id'] for q in queue if q['requirement_id'] not in resolved],
            'unused_search_budget':max(0,limit-searches),'angle_unsupported_reason':unsupported_reason,
            'search_attempts_for_angle':sum(attempts[r] for r in angle_ids),
            'evidence_considered':[s['source_id'] for s in sources]}
    try:
        for source in initial_sources or []:
            key=canonical_url(source['url'])
            if key not in seen and len(sources)<plan['max_sources']:seen.add(key);accept(source)
        # Preflight already attempted these URLs. Failed ones require alternate discovery,
        # not another identical fetch before the requirement queue can run.
        for failure in (resolution or {}).get('failures',[]):
            if failure.get('url'):seen.add(canonical_url(failure['url']))
        while searches<limit:
            pending=[q for q in queue if q['requirement_id'] not in resolved and attempts[q['requirement_id']]<per_requirement]
            pending.sort(key=lambda q:attempts[q['requirement_id']]) # cover each requirement before retrying one
            chosen=None
            for q in pending:
                query=next_query(q,attempts[q['requirement_id']],packet,plan['canonical_topic'])
                if query_key(query) not in query_keys:chosen=(q,query);break
            if not chosen:stop='REQUIREMENT_SEARCH_LIMIT';break
            if fetches>=plan['max_sources']:stop='SOURCE_LIMIT';break
            q,query=chosen;current_requirement=q;rid=q['requirement_id'];budget.check_time()
            if packet and packet.get('comparison_candidate_grounded'):
                subjects=list(dict.fromkeys(subjects+[packet['comparison_evidence']['alternative']]))
            query_keys.add(query_key(query));searches+=1;attempts[rid]+=1
            entry={'search_id':stable_id('search',[plan['idea_id'],searches,query]),'requirement_ids':[rid],
                'category':q['category'],'query':query,'reason':q['question'],
                'results_returned':[],'selected_results':[],'rejected_results':[],
                'search_cost_usd':None,'timestamp':datetime.now(timezone.utc).isoformat()}
            audit.append(entry)
            before=(budget.record.estimated_model_cost_usd,budget.record.estimated_search_cost_usd)
            unknown_before=budget.record.conservative_unknown_cost_usd
            try:
                results=rank_results(provider.search(query,question_id=rid),q,subjects,budget.config,now=plan['planned_at']);entry['results_returned']=results
            except LimitReached:raise
            except Exception as exc:
                entry['error']=type(exc).__name__;failures.append({'stage':'search','search_id':entry['search_id'],'error':type(exc).__name__})
                results=[]
            finally:
                after=(budget.record.estimated_model_cost_usd,budget.record.estimated_search_cost_usd)
                entry['search_cost_usd']=sum(after)-sum(before)
                entry['conservative_unknown_cost_usd']=budget.record.conservative_unknown_cost_usd-unknown_before
                entry['estimated_cost_upper_bound_usd']=entry['search_cost_usd']+entry['conservative_unknown_cost_usd']
                entry['usage_complete']=entry['conservative_unknown_cost_usd']==0
            future_slots=min(limit-searches, sum(attempts[x['requirement_id']]==0 for x in queue if x['requirement_id'] not in resolved))
            fetch_allowance=max(1,min(2,plan['max_sources']-fetches-future_slots))
            added=0;search_fetches=0
            for hit in results:
                if hit.get('selection_rejection'):
                    hit['selected']=False;hit['selection_reason']=hit['selection_rejection']
                    entry['rejected_results'].append({'url':hit['url'],'reason':hit['selection_rejection']});continue
                key=canonical_url(hit['url'])
                if key in seen:
                    hit.update(selected=False,selection_reason='ALREADY_FETCHED_OR_ATTEMPTED')
                    entry['rejected_results'].append({'url':hit['url'],'reason':'ALREADY_FETCHED_OR_ATTEMPTED'});continue
                if search_fetches>=fetch_allowance:
                    hit.update(selected=False,selection_reason='DEFERRED_FOR_REQUIREMENT_COVERAGE')
                    entry['rejected_results'].append({'url':hit['url'],'reason':'DEFERRED_FOR_REQUIREMENT_COVERAGE'});continue
                if fetches>=plan['max_sources']:
                    hit.update(selected=False,selection_reason='SOURCE_LIMIT')
                    entry['rejected_results'].append({'url':hit['url'],'reason':'SOURCE_LIMIT'});continue
                seen.add(key);budget.check_time();fetches+=1;search_fetches+=1
                hit.update(selected=True,selection_reason='HIGHEST_REMAINING_REQUIREMENT_SCORE')
                record={'url':hit['url'],'status':'FETCH_PENDING','selection_score':hit['selection_score']};entry['selected_results'].append(record)
                try:
                    source=provider.fetch(hit['url']).to_dict()
                    if not accept(source):
                        record['status']='REJECTED';hit['selection_reason']=excluded[-1]['reason'];entry['rejected_results'].append(excluded[-1]);continue
                    record.update(status='FETCHED',source_id=source['source_id']);added+=1
                except LimitReached:raise
                except Exception as exc:
                    record['status']='FETCH_FAILED';hit['selection_reason']='FETCH_FAILED'
                    entry['rejected_results'].append({'url':hit['url'],'reason':'FETCH_FAILED'})
                    failures.append({'stage':'fetch','url':hit['url'],'error':type(exc).__name__});continue
            empty=empty+1 if not added else 0
            # Interim synthesis extracts exact passages and resolves requirements after discovery.
            # Unchanged inherited sources do not repeatedly incur synthesis costs.
            if sources and len(sources)!=last_synth_count:
                synthesize()
                if packet['research_status']=='CONTRADICTED':stop='CORE_CONTRADICTION';break
                if packet['research_status']=='SUFFICIENT':stop='EVIDENCE_SUFFICIENT';break
            angle_queue=[q for q in queue if q['category'].startswith('COMPARISON')]
            angle_attempted=all(attempts[q['requirement_id']] for q in angle_queue)
            if empty>=2 and angle_attempted:
                stop='NO_NEW_RELEVANT_EVIDENCE';break
        angle_unresolved=any(q['category'].startswith('COMPARISON') and q['requirement_id'] not in resolved for q in queue)
        angle_attempted=any(attempts[q['requirement_id']] for q in queue if q['category'].startswith('COMPARISON'))
        if angle_unresolved and angle_attempted and (searches>=limit or stop=='NO_NEW_RELEVANT_EVIDENCE'):
            unsupported_reason='SEARCH_BUDGET_EXHAUSTED' if searches>=limit else 'REPEATED_NO_RELEVANT_EVIDENCE'
            stop='ANGLE_UNSUPPORTED'
            if packet:packet.update(early_stop_reason=stop)
        # A non-comparison model suggestion also needs actual unsuccessful research.
        elif angle_reason in ('ANGLE_UNSUPPORTED','ENTITY_UNCORROBORATED') and searches and (searches>=limit or stop=='NO_NEW_RELEVANT_EVIDENCE'):
            unsupported_reason='RESEARCH_ATTEMPTED_WITHOUT_SUFFICIENT_SUPPORT';stop=angle_reason
    except (LimitReached,ProviderFailure,ValueError,KeyError,TypeError) as exc:
        stop=str(exc);failures.append({'stage':'research','error':type(exc).__name__,'reason':str(exc)})
    result=outcome(stop)
    pivot=recommend_pivot(packet,plan,selected,result)
    if pivot:result['editorial_outcome']=pivot['status']
    return packet,sources,result
