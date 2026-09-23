"""Replay persisted evidence locally. No provider, network, model or database writes."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.pivots import recommend_pivot


def replay(folder, output):
    names=('research_packet','research_plan','sources','idea','research_outcome')
    contents={n:(folder/(n+'.json')).read_bytes() for n in names}
    data={n:json.loads(v) for n,v in contents.items()}
    old=data['research_packet'];plan=data['research_plan']
    packet=validate_packet(old,deepcopy(data['sources']),plan,data['idea'])
    pivot=recommend_pivot(packet,plan,data['idea'],data['research_outcome'])
    summary={'original_state':{'research_status':old['research_status'],'stop_reason':data['research_outcome']['stop_reason']},
        'claims':[{'claim_id':c['claim_id'],'text':c['text'],'old_status':old['claims'][i]['status'],
                   'new_status':c['status'],'supported_wording':c.get('supported_wording'),
                   'old_evidence_ids':old['claims'][i]['evidence_ids'],'passage_ids':c['passage_ids'],'evidence_ids':c['evidence_ids'],'passages':c['passages']} for i,c in enumerate(packet['claims'])],
        'requirements':[dict(r,old_status=next(q['status'] for q in plan['requirement_queue'] if q['requirement_id']==r['requirement_id'])) for r in packet['requirement_statuses']],
        'research_status':packet['research_status'],'research_evidence_status':packet['research_evidence_status'],'angle_feasibility_status':packet['angle_feasibility_status'],'comparison_supported':packet.get('comparison_supported',False),
        'angle_outcome':data['research_outcome']['stop_reason'],'pivot':pivot,
        'offline_cost_usd':0,'network_calls':0,'model_calls':0,
        'original_sha256':{n:hashlib.sha256(v).hexdigest() for n,v in contents.items()}}
    output.mkdir(parents=True,exist_ok=True)
    for name,value in [('replay',summary),('research_packet',packet),('evidence_passages',packet['evidence_passages']),('angle_pivot',pivot)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    assert all((folder/(n+'.json')).read_bytes()==v for n,v in contents.items())
    print(json.dumps({k:v for k,v in summary.items() if k not in ('claims','original_sha256')},indent=2))
    return summary

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('saved_run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.saved_run.resolve()==args.output.resolve():parser.error('Output must not overwrite the saved run')
    replay(args.saved_run,args.output)
