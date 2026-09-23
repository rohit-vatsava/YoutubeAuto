"""Re-evaluate persisted preflight evidence without providers, network or DB writes."""
import json
from pathlib import Path
from .resolution import validate_resolution


def replay(directory, config=None):
    directory=Path(directory);config=config or {}
    raw=json.loads((directory/'story_resolution.json').read_text())
    sources=json.loads((directory/'sources.json').read_text())
    selected=json.loads((directory/'idea.json').read_text())
    # Older runs lack raw tool discovery receipts. Do not manufacture them from model URLs.
    discoveries=[dict(e) for e in raw.get('evidence',[]) if e.get('discovery_confirmed')]
    result=validate_resolution(raw,sources,selected,discoveries=discoveries,
        authorities=config.get('resolution_authorities'),score_threshold=config.get('resolution_score_threshold',70))
    result['failures']=raw.get('failures',[])
    if any(f.get('stage')=='story_resolution_fetch' for f in result['failures']):
        result['warnings']=sorted(set(result['warnings']+['SOURCE_FETCH_PARTIAL_FAILURE']))
    result['replay']={'original_status':raw['status'],'network_calls':0,'model_calls':0,
                      'note':'Legacy discovery provenance unavailable unless independently persisted; fetched documents remain usable.'}
    return result
