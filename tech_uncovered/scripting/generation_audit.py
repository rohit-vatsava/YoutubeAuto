"""Commit raw candidates before any normalization or scope gate."""
from copy import deepcopy
from uuid import uuid4
from . import storage
from .pivot_scope import validate_candidate


class ScopeFailure(ValueError):
    def __init__(self,report):
        self.report=report;self.status=report['next_status']
        spans='; '.join(repr(p['text'])+': '+p['reason'] for p in report['rejected_spans'])
        super().__init__(self.status+': '+(spans or 'EDITORIAL_SCOPE_FAILURE: safely phrased angle not produced'))


def capture(db,result,stage,raw):
    assertions=deepcopy(raw.get('propositions',[])) if isinstance(raw,dict) else []
    if not assertions:
        def gather(value):
            if isinstance(value,dict):
                if 'text' in value and 'claim_ids' in value:assertions.append(deepcopy(value))
                else:
                    for child in value.values():gather(child)
            elif isinstance(value,list):
                for child in value:gather(child)
        gather(raw)
    item=dict(candidate_id='candidate-'+str(uuid4()),stage=stage,raw_generated_content=deepcopy(raw),
              generated_factual_assertions=deepcopy(assertions),proposed_claim_mappings=deepcopy(assertions),
              validation_result='PENDING',rejected_spans=[],rejection_reasons=[])
    result.setdefault('generation_candidates',[]).append(item)
    storage.generation_checkpoint(db,result)  # durable BEFORE the validator runs
    return item


def validate(db,result,item,raw,packet,*,draft=False):
    from .pivot_acceptance import scope_issues
    modern=raw.get('scope_contract_version')==2 or result.get('scope_contract_version')==2
    if modern:
        result['scope_contract_version']=2
        candidate=deepcopy(raw)
        if item['stage'] in ('hooks','script_generation'):
            from .generation import sentences
            rows=raw if isinstance(raw,list) else raw.get('hook_candidates',[]) if item['stage']=='hooks' else sentences(raw)
            candidate={'propositions':[dict(text=s['text'],factual=s.get('factual',True),claim_ids=s.get('claim_ids',[]),
                evidence_ids=s.get('source_ids',[]),passage_ids=s.get('evidence_passage_ids',[])) for s in rows]}
            if item['stage']=='script_generation':
                from .generation import scope_propositions
                candidate={'propositions':scope_propositions(raw)}
        if item['stage']=='hooks':
            from .hook_scope import validate_hooks,apply_report
            report=validate_hooks(raw.get('hook_candidates',[]),packet,item['candidate_id'])
            apply_report(raw.get('hook_candidates',[]),report)
        else:
            report=validate_candidate(candidate,packet,item['stage'],item['candidate_id'])
    else:
        issues=scope_issues(raw,packet,draft=draft)
        # Historical providers retain their behavior, but rejected fields are now visible.
        props=[]
        def walk(value,path=''):
            if isinstance(value,dict):
                for key,child in value.items():
                    if key in ('claim_ids','evidence_basis','title_claim_ids'):
                        allowed=packet.get('pivot_acceptance',{}).get('allowed_claim_scope',{})
                        if not isinstance(child,list) or not set(child)<=set(allowed):
                            props.append(dict(text=value.get('text',value.get('angle',repr(child))),field=path+key,
                                factual=True,claim_ids=child,classification='NEW_UNSUPPORTED_CLAIM',reason='Invalid or unauthorized claim-ID mapping: '+repr(child)))
                    walk(child,path+key+'.')
            elif isinstance(value,list):
                for n,child in enumerate(value):walk(child,path+str(n)+'.')
        if issues:walk(raw)
        report=dict(stage=item['stage'],candidate_id=item['candidate_id'],propositions=props,
            result='FAIL' if issues else 'PASS',failure_categories=issues,
            rejected_spans=[{'text':p['text'],'reason':p['reason']} for p in props] or
                ([{'text':str(raw),'reason':', '.join(issues)}] if issues else []),
            next_status='RESEARCH_REQUIRED' if issues else 'CONTINUE')
    if modern and item['stage']=='script_generation' and report['result']=='FAIL' and not raw.get('required_research_assertions'):
        report['next_status']='EDITORIAL_REVIEW'
    item.update(generated_factual_assertions=report['propositions'],proposed_claim_mappings=report['propositions'],
                validation_result=report['result'],rejected_spans=report['rejected_spans'],rejection_reasons=report['failure_categories'])
    result.setdefault('scope_validations',[]).append(report)
    storage.generation_checkpoint(db,result)
    if report['result']=='FAIL' or report['next_status']=='EDITORIAL_REVIEW':raise ScopeFailure(report)
    return report
