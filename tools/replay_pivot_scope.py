"""Local diagnostics only. Never reconstruct a missing provider response."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tech_uncovered.scripting.providers.openai_live import pivot_angle_request,build_payload
from tech_uncovered.scripting.pivot_scope import compact_bundle,validate_candidate
from tech_uncovered.scripting.token_count import count_tokens


def replay(folder,output):
    packet=json.loads((folder/'research_packet.json').read_text())
    cfg=json.loads((folder/'run.json').read_text())['configuration']
    costs=json.loads((folder/'costs.json').read_text())
    bundle=compact_bundle(packet,cfg)
    instructions,data,example=pivot_angle_request(packet,cfg)
    payload=build_payload(cfg,'angle_refinement',instructions,data,example)
    attempts=[a for a in costs['attempts'] if a['stage']=='angle_refinement']
    old=attempts[-1]
    raw_path=folder/'angle_candidate.json'
    raw=json.loads(raw_path.read_text()).get('raw_generated_content') if raw_path.exists() else None
    if raw is None:
        angle=json.loads((folder/'angle.json').read_text())
        if angle is not None:raw=angle
    new_metrics=dict(payload_bytes=len(json.dumps(payload).encode()),input_tokens_local=count_tokens(json.dumps(payload,ensure_ascii=False),cfg),
        evidence_bundle_tokens=count_tokens(json.dumps(bundle,ensure_ascii=False),cfg),historical_context_tokens=0)
    report=dict(source_script_id=folder.name,response_recoverable=raw is not None,
        successful_response_id=old.get('response_id'),
        exact_offending_proposition=None,
        old_decision='RESEARCH_REQUIRED: NEW_UNSUPPORTED_CLAIM',
        old_validator_trigger='Invalid/unauthorized ID or non-list value in claim_ids, evidence_basis or title_claim_ids; not an exact-wording comparison.',
        new_decision=validate_candidate(raw,packet,'angle_refinement','replay-candidate') if raw else 'NOT_EVALUABLE_RESPONSE_NOT_PERSISTED',
        old_metrics={k:old[k] for k in ('payload_bytes','input_tokens_local')},new_metrics=new_metrics,
        payload_reduction_percent=round((1-new_metrics['payload_bytes']/old['payload_bytes'])*100,2),
        token_reduction_percent=round((1-new_metrics['input_tokens_local']/old['input_tokens_local'])*100,2),
        angle_would_pass='UNKNOWN_WITHOUT_ORIGINAL_RESPONSE',
        later_stages_allowed='Only after a newly generated mapped candidate passes; no historical approval inferred.',
        actual_network_calls=0,actual_model_calls=0)
    output.mkdir(parents=True,exist_ok=True)
    for name,value in [('pivot_evidence_bundle',bundle),('angle_request_payload',payload),('replay',report)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('saved_run',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.saved_run.resolve()==args.output.resolve():parser.error('Cannot overwrite original run')
    replay(args.saved_run,args.output)
