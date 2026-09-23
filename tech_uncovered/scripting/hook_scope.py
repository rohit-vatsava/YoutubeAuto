"""Hook sentence composition using the canonical scope classifier."""
from copy import deepcopy
import re
from .pivot_scope import classify,FAILURES

def validate_hooks(hooks,packet,candidate_id):
    results=[]
    for hook in hooks:
        parent=dict(text=hook['text'],factual=hook.get('factual',True),claim_ids=hook.get('claim_ids',[]),
                    evidence_ids=hook.get('source_ids',[]),passage_ids=hook.get('evidence_passage_ids',[]))
        # Sentence boundaries retain inherited IDs; editorial recognition still runs
        # through classify and cannot exempt a factual clause.
        units=[]
        for text in re.split(r'(?<=[.!?])\s+',parent['text']):
            from .scope_language import editorial
            part=dict(parent,text=text)
            if editorial(text,set()):part['factual']=False
            unit=classify(part,packet)
            unit['inherited_claim_ids']=unit.get('claim_ids',[])
            units.append(unit)
        failed=[u for u in units if u['classification'] in FAILURES]
        result=dict(parent,hook_id=hook['hook_id'],atomic_units=units,
                    classification=failed[0]['classification'] if failed else 'SUPPORTED_COMPOSITE_PARAPHRASE',
                    reason='See individually validated sentence units.',
                    polarity_analysis=[x for u in units for x in u.get('polarity_analysis',[])])
        result['inherited_claim_ids']=sorted({cid for u in units if u['classification'] not in FAILURES for cid in u.get('claim_ids',[])})
        results.append(result)
    passing=[r['hook_id'] for r in results if r['classification'] not in FAILURES]
    return dict(stage='hooks',candidate_id=candidate_id,propositions=results,eligible_hook_ids=passing,
                result='PASS' if passing else 'FAIL',next_status='CONTINUE' if passing else 'EDITORIAL_REVIEW',
                failure_categories=sorted({r['classification'] for r in results if r['classification'] in FAILURES}),
                rejected_spans=[dict(text=r['text'],reason=r['reason']) for r in results if r['classification'] in FAILURES])

def apply_report(hooks,report):
    for hook in hooks:
        hook['scope_eligible']=hook['hook_id'] in report['eligible_hook_ids']
    return hooks
