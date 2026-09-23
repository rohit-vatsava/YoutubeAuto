"""Offline ranking/cost counterfactual using immutable saved artifacts."""
import json
from pathlib import Path
from .source_selection import rank_results,score_result
from .providers.openai_live import build_payload,ModelResearchSynthesizer
from .token_count import count_tokens
from .costs import Budget


def replay(directory,config):
    folder=Path(directory)
    load=lambda name:json.loads((folder/(name+'.json')).read_text())
    search=load('research_searches')[0];plan=load('research_plan');sources=load('sources');selected=load('idea');cost=load('costs')
    subject=plan['story_resolution']['canonical_subject']
    products=plan['story_resolution'].get('identifiers',{}).get('products',[])
    ranked=rank_results(search['results_returned'],{'category':search['category']},[subject]+products,config,now=plan['planned_at'])
    failures={e.get('url','').rstrip('/') for e in plan['story_resolution'].get('failures',[])}
    selectable=[r for r in ranked if not r['selection_rejection'] and r['canonical_url'] not in failures]
    post=[score_result({'url':s['url']},{'category':search['category']},[subject]+products,config,source=s,now=plan['planned_at']) for s in sources]
    class PayloadCapture:
        def request(self,stage,instructions,data,example):return build_payload(config,stage,instructions,data,example)
    payload=ModelResearchSynthesizer(PayloadCapture()).synthesize(plan,sources,selected)
    serialized=json.dumps(payload,ensure_ascii=False);tokens=count_tokens(serialized,config)
    size=len(json.dumps(payload).encode())
    budget=Budget(config)
    budget.record.estimated_model_cost_usd=sum(x.get('estimated_model_cost_usd',0) for x in cost['attempts'])
    budget.record.estimated_search_cost_usd=sum(x.get('billed_search_calls',0)*cost['pricing']['search_per_call'] for x in cost['attempts'])
    budget._sync();known=budget.record.known_cost_usd
    reserve=budget.reserve(tokens,payload_bytes=size,stage='reconstructed_synthesis')
    budget.unknown('reconstructed_synthesis',reserve)
    remaining_time=config['max_research_seconds']-cost['total_research_seconds']
    return {'mode':'OFFLINE_COUNTERFACTUAL','network_calls':0,'model_calls':0,
        'old_ranking':search['results_returned'],'old_selected':search['selected_results'],
        'new_ranking':ranked,'next_fetch_candidates':[r['url'] for r in selectable[:2]],
        'post_fetch_classification':post,
        'cost_reconstruction':{'known_cost_usd':known,'local_input_tokens':tokens,'encoding':config['tokenizer_encoding'],
            'payload_bytes':size,'protocol_token_reserve':config.get('tokenizer_protocol_reserve',1024),
            'reserved_cost_usd':reserve,'conservative_unknown_cost_usd':reserve,
            'estimated_cost_upper_bound_usd':budget.record.estimated_cost_upper_bound_usd,
            'upper_bound_with_one_retry_usd':budget.record.estimated_cost_upper_bound_usd+reserve,
            'retry_budget_fits':budget.can_reserve(reserve),'remaining_research_seconds':remaining_time,
            'retry_time_fits':remaining_time>=config['request_timeout_seconds'],
            'old_unknown_reservation_logged':False,
            'note':'Counterfactual reservation from the saved plan/sources/idea and current request builder. Original wire payload/reservation was not logged; this is not recovered historical billing.'}}
