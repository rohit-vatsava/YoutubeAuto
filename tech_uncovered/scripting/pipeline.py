from uuid import uuid4
from .costs import Budget
from .planning import BoundedResearchPlanner
from .research import collect
from .generation import normalize_draft
from .fact_check import validate_check
from .quality import review_quality
from .readiness import decide
from . import storage
from .resolution import StoryResolutionGate


def run(db,selected,config,provider,synthesizer,generator,checker,reviewer,budget,now,mode,resume=None,stop_after=None):
    sid='script-'+str(uuid4());rid='research-'+str(uuid4())
    result={'script_id':sid,'research_run_id':rid,'created_at':now,'mode':mode,'selected':selected,
            'plan':BoundedResearchPlanner().plan(selected,config,now),'packet':None,'sources':[],
            'draft':None,'check':None,'quality':None,'angle':None,'outline':None,'revisions':[],'failures':[]}
    if resume:
        from copy import deepcopy
        saved=deepcopy(resume['snapshot'])
        result.update({k:v for k,v in saved.items() if k not in ('script_id','research_run_id','created_at','failures','readiness','cost','resume_snapshot','resume_metadata')})
        result['resume_metadata']=dict(resumed_from_script_id=saved['script_id'],resumed_at=now,
            source_research_run_id=(saved.get('packet') or {}).get('source_research_run_id',saved['research_run_id']),
            stages_reused=list(saved.get('completed_stages',[])),stages_executed=[],boundaries_executed=[])
        if result.get('packet'):
            result['packet'].update(source_research_run_id=result['resume_metadata']['source_research_run_id'],
                research_run_id=rid,research_packet_id='packet-'+str(uuid4()))
    result['_stop_after']=stop_after
    result['configuration']=config
    result['providers']={name:{'name':part.name,'version':part.version} for name,part in (('research',provider),('synthesizer',synthesizer),('generator',generator),('checker',checker),('reviewer',reviewer))}
    storage.start(db,result,config,provider.name+':'+provider.version)
    try:
        if result.get('packet'):
            packet=result['packet'];sources=result['sources'];outcome=result['research_outcome']
        else:
            if 'story_resolution' in result.get('completed_stages',[]):
                resolution=result['story_resolution'];preflight_sources=result['sources']
            else:
                with budget.stage('story_resolution_cost'):
                    resolution,preflight_sources=StoryResolutionGate().resolve(selected,provider,budget,config)
                result['story_resolution']=resolution
                result['sources']=preflight_sources
                result['plan']['story_resolution']=resolution
                storage.boundary(db,result,'story_resolution')
            if resolution['status']=='RESOLVED':
                from .requirements import prepare
                prepare(result['plan'],selected)
                with budget.stage('full_research_cost'):
                    packet,sources,outcome=collect(provider,synthesizer,result['plan'],selected,budget,initial_sources=preflight_sources)
            else:
                packet,sources,outcome=None,preflight_sources,{'stop_reason':'STORY_UNRESOLVED','logical_search_calls':0,'failures':resolution['failures']}
            result.update(packet=packet,sources=sources,research_outcome=outcome)
            if packet:packet.update(research_packet_id='packet-'+str(uuid4()),research_run_id=rid,
                                   radar_run_id=selected['radar_run_id'],intelligence_run_id=selected['intelligence_run_id'],created_at=now)
        # Commit the packet before any generator call, including angle refinement.
        storage.save_research(db,result)
        storage.boundary(db,result,'research')
        result['failures'].extend(outcome['failures']);budget.finish_research();generation_start=budget.clock()
        generate_from_packet(db,result,config,generator,checker,reviewer,budget,now,
            reused_angle=result.get('angle') if resume else None,
            reused_outline=result.get('outline') if resume else None,
            reused_generation=result.get('raw_generation') if resume else None,
            reused_check=result.get('check') if resume else None,
            reused_quality=result.get('quality') if resume else None)
        budget.record.total_generation_seconds=budget.clock()-generation_start
    except storage.PipelinePaused as exc:
        result['_paused']=str(exc)
    except Exception as exc:
        result['failures'].append({'stage':'pipeline','error':type(exc).__name__,'reason':str(exc) if isinstance(exc,ValueError) else 'Stage failed; prior committed evidence retained'})
        if budget.research_active:budget.finish_research()
        else:budget.record.total_generation_seconds=budget.clock()-generation_start
    result['readiness']=decide(result['packet'],result['draft'],result['check'],result['quality'],result['angle'] or {},config)
    if result.get('angle',{}) and result['angle'].get('originality_status')=='REJECT':result['readiness']={'status':'REJECTED','reasons':['ORIGINALITY_REJECTION']}
    if result.get('story_resolution',{}).get('status')!='RESOLVED':
        result['readiness']['reasons'].append('STORY_UNRESOLVED')
    if result.get('_paused'):result['readiness']={'status':'PAUSED','reasons':[result['_paused']]}
    result['cost']=budget.record.to_dict();storage.finish(db,result)
    return result


def generate_from_packet(db,result,config,generator,checker,reviewer,budget,now,reused_angle=None,reused_outline=None,reused_generation=None,reused_check=None,reused_quality=None):
    from copy import deepcopy
    packet=result['packet'];selected=deepcopy(result['selected']);sid=result['script_id']
    if packet and packet.get('pivot_acceptance'):
        if getattr(generator,'scope_contract_version',None)==2:result['scope_contract_version']=2
        selected['idea']['proposed_angle']=packet['pivot_acceptance']['accepted_angle']
        selected['idea']['required_research']=[]
    if getattr(generator,'scope_contract_version',None)==2:result['scope_contract_version']=2
    from .generation_audit import capture, validate
    def audit(stage,value,draft=False):
        item=capture(db,result,stage,value)
        if packet.get('pivot_acceptance') or result.get('scope_contract_version')==2:validate(db,result,item,value,packet,draft=draft)
        else:
            item['validation_result']='NOT_APPLICABLE_NON_PIVOT';storage.generation_checkpoint(db,result)
    def executing(stage):
        if result.get('resume_metadata'):
            result['resume_metadata']['stages_executed'].append(stage)
            storage.generation_checkpoint(db,result)
    if packet and packet['research_status']=='SUFFICIENT':
        if reused_angle is not None:angle=deepcopy(reused_angle)
        else:
            with budget.stage('script_generation_cost'):
                angle=generator.refine(packet,selected)
            audit('angle_refinement',angle)
            if angle.get('scope_contract_version')==2:
                from .pivot_scope import validated_angle
                angle=validated_angle(angle,result['scope_validations'][-1])
        angle['original_proposed_angle']=selected['idea']['proposed_angle']
        valid_ids={c['claim_id'] for c in packet['claims'] if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')}
        if not angle.get('evidence_basis') or not set(angle['evidence_basis'])<=valid_ids:raise ValueError('Angle has no valid evidence basis')
        result['angle']=angle
        storage.boundary(db,result,'angle')
        if angle.get('originality_status')!='REJECT':
            if reused_outline is not None:
                outline=deepcopy(reused_outline)
            else:
                with budget.stage('script_generation_cost'):
                    executing('script_outline')
                    outline=generator.outline(packet,angle)
                audit('script_outline',outline)
            result['outline']=outline;storage.boundary(db,result,'outline');feedback=None
            for revision in range(1,config['max_revision_attempts']+2):
                if reused_generation is not None and revision==1:
                    raw=deepcopy(reused_generation)
                else:
                    with budget.stage('script_generation_cost'):
                        executing('script_generation')
                        raw=generator.generate(packet,angle,outline,feedback)
                result['raw_generation']=raw
                storage.boundary(db,result,'generation')
                # Capture BOTH artifacts before hook scoring, normalization or validation.
                script_item=capture(db,result,'script_generation',raw)
                hooks_item=capture(db,result,'hooks',{'hook_candidates':raw.get('hook_candidates',[])})
                if packet.get('pivot_acceptance') or result.get('scope_contract_version')==2:
                    validate(db,result,hooks_item,{'hook_candidates':raw.get('hook_candidates',[])},packet)
                    storage.boundary(db,result,'hooks')
                    validate(db,result,script_item,raw,packet,draft=True)
                draft=normalize_draft(raw,packet,angle,config,sid,revision)
                storage.save_draft(db,draft);result['draft']=draft;result['check']=None;result['quality']=None
                storage.boundary(db,result,'script')
                with budget.stage('fact_check_cost'):
                    if reused_check is None:executing('script_fact_check')
                    from copy import deepcopy
                    check=validate_check(deepcopy(reused_check) if reused_check is not None else checker.check(draft,packet,angle,now),draft,packet,now)
                result['check']=check;storage.save_review(db,'script_fact_checks',check)
                storage.boundary(db,result,'fact_check')
                if check['verdict'] in ('FAIL','RESEARCH_REQUIRED'):
                    return
                with budget.stage('quality_review_cost'):
                    if reused_quality is None:executing('editorial_review')
                    quality=review_quality(deepcopy(reused_quality) if reused_quality is not None else reviewer.review(draft,packet,selected),draft)
                result['quality']=quality;storage.save_review(db,'script_quality_reviews',quality)
                storage.boundary(db,result,'quality_review')
                readiness=decide(packet,draft,check,quality,angle,config)
                result['revisions'].append({'draft':draft,'check':check,'quality':quality,'readiness':readiness})
                # Only editorial changes get one bounded revision. Research failures never force a rewrite.
                if readiness['status']!='EDITORIAL_REVIEW':break
                feedback={'check':check,'quality':quality,'readiness':readiness}


def run_accepted_pivot(db,candidate,config,generator,checker,reviewer,budget,now,mode='live',resume=None,stop_after=None):
    """No ResearchProvider/Synthesizer exists on this execution path."""
    from copy import deepcopy
    from .pivot_acceptance import accept, SKIPPED
    if resume:
        packet=deepcopy(resume['packet']);acceptance=deepcopy(packet['pivot_acceptance'])
    else:acceptance,packet=accept(candidate,now)
    sid='script-'+str(uuid4());rid='research-'+str(uuid4())
    selected=deepcopy(candidate['selected'])
    # Preserve the complete original selection separately in the acceptance lineage.
    result=dict(script_id=sid,research_run_id=rid,created_at=now,mode=mode,selected=selected,
        plan={'idea_id':packet['idea_id'],'canonical_topic':packet['topic'],'freshness_requirement':{'mode':'EVERGREEN'},
              'source_research_run_id':acceptance['source_research_run_id'],'pivot_acceptance':acceptance},
        packet=packet,sources=packet['source_records'],draft=None,check=None,quality=None,angle=None,outline=None,
        revisions=[],failures=[],configuration=config,pivot_acceptance=acceptance,
        story_resolution={'status':'SKIPPED_ACCEPTED_PIVOT'},
        research_outcome={'stop_reason':'ACCEPTED_PIVOT_REUSE','logical_search_calls':0,'failures':[],
                          'stages_skipped':SKIPPED,'source_research_run_id':acceptance['source_research_run_id']},
        providers={name:{'name':part.name,'version':part.version} for name,part in
                   (('generator',generator),('checker',checker),('reviewer',reviewer))})
    packet.update(research_packet_id='packet-'+str(uuid4()),research_run_id=rid,
        radar_run_id=selected['radar_run_id'],intelligence_run_id=selected['intelligence_run_id'],created_at=now)
    if resume:
        result['resume_metadata']=dict(resumed_from_script_id=resume['run']['script_id'],resumed_at=now,
            source_research_run_id=acceptance['source_research_run_id'],reused_research_run_id=resume['packet']['research_run_id'],
            stages_reused=['accepted_research_packet','pivot_acceptance','angle_refinement'],stages_executed=[])
        result['scope_contract_version']=2
        result['angle']=deepcopy(resume['angle'])
        result['scope_validations']=[deepcopy(resume['validation'])]
        if resume.get('outline') is not None:
            result['outline']=deepcopy(resume['outline'])
            result['scope_validations'].append(deepcopy(resume['outline_validation']))
            result['resume_metadata']['stages_reused'].append('script_outline')
        if resume.get('generation') is not None:
            result['resume_metadata']['stages_reused'].extend(['script_generation','hooks'])
        result['research_outcome']['stages_skipped']=SKIPPED+['angle_refinement']+(['script_outline'] if resume.get('outline') is not None else [])
    result['_stop_after']=stop_after
    storage.start(db,result,config,'accepted-pivot-reuse')
    if resume:storage.generation_checkpoint(db,result)
    storage.save_research(db,result)
    budget.finish_research();budget.record.total_research_seconds=0
    start=budget.clock()
    try:
        storage.boundary(db,result,'pivot')
        generate_from_packet(db,result,config,generator,checker,reviewer,budget,now,reused_angle=resume['angle'] if resume else None,reused_outline=resume.get('outline') if resume else None,reused_generation=resume.get('generation') if resume else None)
    except storage.PipelinePaused as exc:
        result['_paused']=str(exc)
    except Exception as exc:
        from .generation_audit import ScopeFailure
        if isinstance(exc,ScopeFailure):result['scope_failure_status']=exc.status
        result['failures'].append({'stage':'pivot_generation','error':type(exc).__name__,
            'reason':str(exc) if isinstance(exc,ValueError) else 'Generation/review stopped; saved evidence retained'})
    budget.record.total_generation_seconds=budget.clock()-start
    result['readiness']=decide(packet,result['draft'],result['check'],result['quality'],result['angle'] or {},config)
    if result.get('angle') and result['angle'].get('originality_status')=='REJECT':
        result['readiness']={'status':'REJECTED','reasons':['ORIGINALITY_REJECTION']}
    if result['failures']:result['readiness']={'status':result.get('scope_failure_status','RESEARCH_REQUIRED'),'reasons':['EDITORIAL_SCOPE_FAILURE' if result.get('scope_failure_status')=='EDITORIAL_REVIEW' else 'PIVOT_GENERATION_OR_SCOPE_INCOMPLETE']}
    if result.get('_paused'):result['readiness']={'status':'PAUSED','reasons':[result['_paused']]}
    result['cost']=budget.record.to_dict();storage.finish(db,result)
    return result
