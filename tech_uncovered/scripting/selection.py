import json
import math
from ..intelligence.models import digest


def select_ideas(db, intelligence_run_id=None, idea_id=None, top=1, *, prefer_researchable=False, score_window=7, include_backlog=False):
    if top < 1:raise ValueError('--top must be positive')
    rows=list(db.connection.execute('SELECT * FROM intelligence_runs WHERE expired=0 ORDER BY rowid DESC'))
    run=None
    for row in rows:
        if intelligence_run_id:
            if row['intelligence_run_id']==intelligence_run_id:run=row;break
        elif row['status']=='complete' and row['mode']!='synthetic':run=row;break
    if run is None:raise ValueError('No matching retained Intelligence run; no alternate run substituted')
    from ..intelligence.editorial import eligible, story_fields, researchability_fields, story_first
    from ..intelligence.entry_contract import assess
    candidates=[]
    for row in db.connection.execute('SELECT payload FROM idea_candidates WHERE intelligence_run_id=?',(run['intelligence_run_id'],)):
        idea=json.loads(row[0])
        if idea_id and idea.get('idea_id')!=idea_id:continue
        if not eligible(idea, include_backlog=include_backlog):continue
        if idea.get('duplicate_of') or idea.get('similarity_status')=='REJECT' or 'REJECT_NEAR_DUPLICATE' in idea.get('risk_flags',[]):continue
        if not all(idea.get(k) for k in ('idea_id','topic','audience_question','source_video_ids','radar_run_id')):continue
        if not isinstance(idea.get('idea_score'),(int,float)) or not math.isfinite(idea['idea_score']):continue
        if idea.get('intelligence_run_id')!=run['intelligence_run_id'] or idea['radar_run_id']!=run['radar_run_id']:
            raise ValueError('Idea provenance does not match selected run')
        refs=[];radar_metadata=[]
        for vid in idea['source_video_ids']:
            item=db.connection.execute('SELECT payload FROM intelligence_candidates WHERE intelligence_run_id=? AND source_video_id=?',(run['intelligence_run_id'],vid)).fetchone()
            if not item:raise ValueError('Source snapshot missing; provenance cannot be reconstructed')
            v=json.loads(item[0]);radar_metadata.append({k:v.get(k) for k in ('video_id','published_at','observed_at','views','duration_seconds','cohort')})
            refs.append({'video_id':vid,'title':v['title'],'url':v['url'],'observed_at':v['observed_at'],
                                               'channel':v['channel'],'snapshot_hash':v['snapshot_hash']})
        cluster=db.connection.execute('SELECT payload FROM trend_clusters WHERE intelligence_run_id=? AND cluster_id=?',(run['intelligence_run_id'],idea['cluster_id'])).fetchone()
        if not cluster:raise ValueError('Source trend missing')
        candidates.append({'idea':idea,'idea_snapshot_hash':digest(idea),'competitor_references':refs,
                            'trend':json.loads(cluster[0]),'radar_metadata':radar_metadata,'intelligence_run_id':run['intelligence_run_id'],
                            'radar_run_id':run['radar_run_id'],'source_observed_at':run['source_observed_at'],'mode':run['mode']})
    candidates.sort(key=lambda c:(c['idea'].get('rank') is None,c['idea'].get('rank') or 0,-c['idea']['idea_score'],c['idea']['idea_id']))
    if not candidates:raise ValueError('No eligible non-rejected idea in selected Intelligence run')
    from .resolution import assess_researchability
    for candidate in candidates:
        candidate.update(assess_researchability(candidate))
        candidate.update(assess(candidate['idea']))
        candidate.update(story_fields(candidate['idea'], candidate['trend']))
        candidate.update(researchability_fields(candidate['idea'], candidate['researchability_score']))
        candidate['stored_editorial_state'] = candidate['idea']['category']
        candidate['editorial_state'] = ('BACKLOG' if not candidate['story_requirement_satisfied'] and candidate['idea']['category']=='RECOMMENDED FOR RESEARCH' else candidate['idea']['category'])
    if prefer_researchable and not idea_id:
        return story_first(candidates, top, score_window)
    return candidates[:1 if idea_id else top]
