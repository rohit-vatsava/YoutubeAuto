"""Offline planning replay, without search results, provider construction or DB writes."""
import json
from pathlib import Path
from .planning import BoundedResearchPlanner
from .requirements import prepare,next_query


def preview(directory,config):
    directory=Path(directory)
    selected=json.loads((directory/'idea.json').read_text())
    old_plan=json.loads((directory/'research_plan.json').read_text())
    resolution=json.loads((directory/'story_resolution.json').read_text())
    plan=BoundedResearchPlanner().plan(selected,config,old_plan['planned_at'])
    plan['story_resolution']=resolution
    queue=prepare(plan,selected)
    return {'mode':'OFFLINE_PLANNING_REPLAY','network_calls':0,'model_calls':0,
        'old_outcome':json.loads((directory/'research_outcome.json').read_text()),
        'requirements_before_research':queue,'claims_to_verify':plan['claims_to_verify'],
        'planned_searches':[{'slot':i+1,'requirement_ids':[q['requirement_id']], 'category':q['category'],
                            'query':next_query(q,0,None,plan['canonical_topic'])}
                           for i,q in enumerate(queue[:plan['max_search_calls']])],
        'limits':{k:config[k] for k in ('max_search_calls','max_sources','max_model_cost_usd','max_research_seconds','max_searches_per_requirement')},
        'note':'Queries only: future results/evidence are unknown. The fourth query adapts only to a passage-grounded alternative and criterion. Preflight has its separate one-search cap; both stages share the cost/time ledger.'}
