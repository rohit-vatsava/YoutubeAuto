"""Read saved M3 artifacts and replay local validation; no providers or DB writes."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.scripting.fact_check import validate_check
from tech_uncovered.scripting.readiness import decide
from tech_uncovered.scripting.generation import scope_propositions
from tech_uncovered.scripting.pivot_scope import validate_candidate


def replay(folder,output):
    if folder.resolve()==output.resolve():raise ValueError('Output must not overwrite saved run')
    names=('run','research_packet','script','fact_check','quality_review','angle')
    saved={n:(folder/(n+'.json')).read_bytes() for n in names}
    data={n:json.loads(v) for n,v in saved.items()}
    packet=data['research_packet'];draft=data['script'];cfg=data['run']['configuration']
    checked=validate_check(deepcopy(data['fact_check']),draft,packet,data['fact_check']['checked_at'])
    status=decide(packet,draft,checked,data['quality_review'],data['angle'],cfg)
    scope=validate_candidate({'propositions':scope_propositions(draft)},packet,'script_generation','offline-replay')
    report=dict(script_id=folder.name,blocking_issues=checked['blocking_issues'],observations=checked['observations'],
        fact_check_verdict=checked['verdict'],scope_result=scope['result'],readiness=status,
        word_count=draft['word_count'],word_max=cfg['script_word_max'],
        word_count_status='EDITORIAL_REVIEW' if draft['word_count']>cfg['script_word_max'] else 'WITHIN_LIMIT',
        estimated_duration=draft['estimated_duration'],quality_review_present=data['quality_review'] is not None,
        originality_status=data['angle'].get('originality_status'),
        note='Legacy findings stay blocking. No prose-based reclassification, content changes, or review verdict upgrades.',
        network_calls=0,model_calls=0,search_calls=0,fetch_calls=0,cost_usd=0,
        original_sha256={n:hashlib.sha256(v).hexdigest() for n,v in saved.items()})
    output.mkdir(parents=True,exist_ok=True)
    for name,value in [('replay',report),('normalized_fact_check',checked),('scope_validation',scope)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    assert all((folder/(n+'.json')).read_bytes()==v for n,v in saved.items())
    print(json.dumps({k:v for k,v in report.items() if k not in ('blocking_issues','observations','original_sha256')},indent=2))
    print('Blocking findings:',len(report['blocking_issues']),'Observations:',len(report['observations']))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('saved_run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    replay(args.saved_run,args.output)
