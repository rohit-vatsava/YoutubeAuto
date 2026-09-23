"""Revalidate an exact saved angle locally, preserving all original artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.scripting.pivot_scope import validate_candidate,validated_angle


def replay(folder,output):
    names=('angle_candidate','scope_validation','research_packet')
    original={name:(folder/(name+'.json')).read_bytes() for name in names}
    values={name:json.loads(data) for name,data in original.items()}
    candidate=values['angle_candidate'];raw=candidate['raw_generated_content'];packet=values['research_packet']
    old=values['scope_validation'];new=validate_candidate(raw,packet,'angle_refinement',candidate['candidate_id'])
    angle=validated_angle(raw,new) if new['result']=='PASS' and new['next_status']=='CONTINUE' else None
    verified={c['claim_id'] for c in packet['claims'] if c['status'] in ('VERIFIED','PARTIALLY_VERIFIED')}
    proceed=bool(angle and angle.get('evidence_basis') and set(angle['evidence_basis'])<=verified and angle.get('originality_status')!='REJECT')
    report=dict(source_run=folder.name,candidate_id=candidate['candidate_id'],
        propositions=[dict(text=p['text'],old_classification=old['propositions'][i]['classification'],
                           new_classification=p['classification']) for i,p in enumerate(new['propositions'])],
        atomic_units=new['propositions'][1].get('atomic_units',[]),polarity_analysis=new['propositions'][3].get('polarity_analysis',[]),
        old_result=old['result'],old_next_status=old['next_status'],new_result=new['result'],new_next_status=new['next_status'],
        original_evidence_basis=raw.get('evidence_basis'),validated_evidence_basis=angle.get('evidence_basis') if angle else None,
        would_reach_outline_generation=proceed,outline_generated=False,
        source_sha256={name:hashlib.sha256(data).hexdigest() for name,data in original.items()},
        actual_network_calls=0,actual_model_calls=0,actual_research_calls=0)
    output.mkdir(parents=True,exist_ok=True)
    for name,value in [('scope_validation',new),('validated_angle',angle),('replay',report)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    assert all((folder/(name+'.json')).read_bytes()==data for name,data in original.items())
    print(json.dumps(report,indent=2,ensure_ascii=False));return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('saved_run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.saved_run.resolve()==args.output.resolve():parser.error('Output must not overwrite the original run')
    replay(args.saved_run,args.output)
