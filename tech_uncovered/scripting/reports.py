import json
from pathlib import Path


def export(result,directory):
    root=Path(directory);folder=root/result['script_id'];folder.mkdir(parents=True,exist_ok=True)
    artifacts={'research_searches':result.get('research_outcome',{}).get('research_searches',[]),'story_resolution':result.get('story_resolution'),'idea':result['selected'],'research_plan':result['plan'],'research_packet':result['packet'],
               'sources':result['sources'],'claims':result['packet']['claims'] if result['packet'] else [],
               'angle':result['angle'],'outline':result['outline'],'hooks':result['draft']['hook_candidates'] if result['draft'] else [],
               'script':result['draft'],'fact_check':result['check'],'quality_review':result['quality'],
               'costs':result['cost'],'readiness':result['readiness'],'research_outcome':result.get('research_outcome'),
               'failures':result['failures'],'run':{k:result[k] for k in ('script_id','research_run_id','created_at','mode','configuration','providers')}}
    if result.get('resume_snapshot'):artifacts['pipeline_snapshot']=result['resume_snapshot']
    artifacts['evidence_passages']=(result.get('packet') or {}).get('evidence_passages',[])
    if result.get('pivot_acceptance'):artifacts['pivot_acceptance']=result['pivot_acceptance']
    artifacts['angle_pivot']=(result.get('packet') or {}).get('angle_pivot')
    if result.get('resume_metadata'):artifacts['resume_metadata']=result['resume_metadata']
    validations=result.get('scope_validations',[])
    artifacts['scope_validation']=validations[-1] if validations else None
    artifacts['scope_validations']=validations
    names={'angle_refinement':'angle_candidate','script_outline':'outline_candidate','hooks':'hooks_candidate','script_generation':'script_candidate'}
    counts={}
    for candidate in result.get('generation_candidates',[]):
        name=names[candidate['stage']];counts[name]=counts.get(name,0)+1
        artifacts[name]=candidate;artifacts[name+'-'+str(counts[name])]=candidate
    artifacts['generation_metrics']=[{k:attempt.get(k) for k in ('stage','input_tokens_local','payload_bytes','evidence_bundle_tokens','historical_context_tokens')} for attempt in result['cost'].get('attempts',[]) if attempt['stage'] in ('angle_refinement','script_outline','script_generation','script_fact_check','editorial_review')]
    for name,value in artifacts.items():(folder/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')
    for rev in result['revisions']:
        (folder/f"revision-{rev['draft']['revision']}.json").write_text(json.dumps(rev,indent=2,ensure_ascii=False)+'\n')
    packet=result['packet'] or {};draft=result['draft'] or {};quality=result['quality'] or {};check=result['check'] or {}
    text='# Tech Uncovered — Script Candidate\n\n'
    if result['mode']=='synthetic':text+='**FICTIONAL OFFLINE FIXTURE — NOT A REAL STORY**\n\n'
    sections={'STATUS':result['readiness']['status'],'IDEA':result['selected']['idea']['proposed_angle'],
              'WHY NOW':packet.get('why_now','Unresolved'),'RESEARCH SUMMARY':packet.get('confirmed_story','No verified packet'),
              'KEY SOURCES':'\n'.join('- '+s['title']+' — '+s['url'] for s in result['sources']),
              'SELECTED ANGLE':(result['angle'] or {}).get('angle','Not generated'),
              'HOOK':draft.get('selected_hook',{}).get('text','Not generated'),
              'SCRIPT':draft.get('full_script','No script generated; evidence or review gates were not met.'),
              'FACT CHECK':check.get('verdict','Not performed'),'QUALITY SCORE':str(quality.get('score','Not performed')),
              'RESEARCH / EDITORIAL WARNINGS':json.dumps({'gates':result['readiness']['reasons'],'failures':result['failures'],'spoken_naturalness':quality.get('spoken_naturalness',{})},ensure_ascii=False)}
    text+='\n\n'.join('## '+k+'\n\n'+v for k,v in sections.items())+'\n'
    (folder/'script.md').write_text(text);(root/'latest.md').write_text(text)
    return folder


def expire_reports(directory,now):
    import shutil
    from datetime import timedelta
    from .claims import time
    root=Path(directory)
    if not root.exists():return
    removed=False
    for folder in root.glob('script-*'):
        if not folder.is_dir() or folder.is_symlink():continue
        path=folder/'idea.json'
        if not path.exists():continue
        try:
            selected=json.loads(path.read_text())
            if selected.get('mode')!='synthetic' and time(selected['source_observed_at'])<=now-timedelta(days=30):
                shutil.rmtree(folder);removed=True
        except (ValueError,KeyError,OSError):continue
    if removed:(root/'latest.md').unlink(missing_ok=True)
