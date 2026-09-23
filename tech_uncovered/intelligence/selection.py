import json
import math
from .models import digest
from ..settings import parse_time


def select_candidates(db, run_id=None, top=30, ordering=None, *, quality_band=7):
    if top <= 0:
        raise ValueError('--top must be positive')
    runs = list(db.connection.execute('SELECT rowid AS insertion_order,* FROM research_runs ORDER BY rowid DESC'))
    selected = None
    for run in runs:
        metadata = json.loads(run['payload'])
        if (run_id and run['run_id'] == run_id) or (not run_id and metadata.get('mode') == 'live' and metadata.get('status') == 'complete'):
            selected = (run, metadata)
            break
    if not selected:
        raise ValueError('Requested Radar run not found' if run_id else 'No complete live Radar run found; provide --run-id for an existing offline/synthetic run')
    run, metadata = selected
    candidates, failures = [], []
    topics = {}
    for row in db.connection.execute('SELECT payload FROM topic_groups WHERE run_id=?', (run['run_id'],)):
        group = json.loads(row['payload'])
        for evidence in group.get('evidence', []):
            topics.setdefault(evidence['video_id'], []).append(group['theme'])
    for stored in db.connection.execute('SELECT payload FROM video_scores WHERE run_id=?', (run['run_id'],)):
        try:
            video = json.loads(stored['payload'])
            if not isinstance(video, dict):
                raise ValueError('Snapshot must be an object')
            if video.get('eligibility_reason') != 'eligible' or video.get('provisional') or video.get('velocity_adjusted_score') is None:
                continue
            for key in ('velocity_adjusted_score', 'outlier_ratio', 'velocity_ratio', 'percentile'):
                if not isinstance(video[key], (float, int)) or not math.isfinite(video[key]) or video[key] < 0:
                    raise ValueError('Invalid score')
            for key in ('video_id', 'channel_id', 'channel', 'title', 'url', 'published_at', 'observed_at', 'duration_seconds', 'cohort'):
                if key not in video:
                    raise ValueError('Missing candidate field')
            for key in ('video_id','channel_id','channel','title','url','published_at','observed_at','cohort'):
                if not isinstance(video[key], str) or not video[key]:
                    raise ValueError('Invalid candidate text field')
            if not isinstance(video['duration_seconds'], (float,int)) or not math.isfinite(video['duration_seconds']) or video['duration_seconds'] <= 0:
                raise ValueError('Invalid duration')
            parse_time(video['published_at'])
            parse_time(video['observed_at'])
            source_hash = digest(video)
            video['radar_run_id'] = run['run_id']
            video['channel_name'] = video['channel']
            video['radar_topics'] = video.get('radar_topics', topics.get(video['video_id'], []))
            video['snapshot_hash'] = source_hash
            candidates.append(video)
        except (ValueError, TypeError, KeyError):
            failures.append({'stage': 'selection', 'video_id': None, 'reason': 'Invalid candidate snapshot skipped'})
    ordering = ordering or ['opportunity_score', 'researchability_score', 'velocity_adjusted_score']
    allowed = {'opportunity_score', 'researchability_score', 'velocity_adjusted_score'}
    if not ordering or len(set(ordering)) != len(ordering) or set(ordering) - allowed:
        raise ValueError('Invalid selection ordering')
    def key(v):
        rich = 'opportunity_score' in v
        values = [v.get(k) for k in ordering]
        if any(x is not None and (not isinstance(x, (int, float)) or not math.isfinite(x)) for x in values):
            raise ValueError('Invalid opportunity score')
        return (rich and v.get('production_fit') == 'POOR',
                *[-x if x is not None else float('inf') for x in values],
                -bool(v.get('named_entity_hints')), -bool(v.get('event_hints')),
                -v['outlier_ratio'], v['video_id'])
    candidates.sort(key=key)
    if not isinstance(quality_band, (int, float)) or not math.isfinite(quality_band) or quality_band < 0:
        raise ValueError('Invalid intake quality band')
    # Modern Radar intake is limited to scored current opportunities. Preserve
    # the legacy fixture path where opportunity fields do not exist at all.
    modern = any('opportunity_score' in v for v in candidates)
    pool = [v for v in candidates if v.get('opportunity_score') is not None] if modern else candidates
    cohort_counts = {}
    for rank, video in enumerate(candidates, 1):
        cohort = video.get('market_cohort', 'UNASSIGNED')
        cohort_counts[cohort] = cohort_counts.get(cohort, 0)+1
        video.update(global_rank=rank, cohort_rank=cohort_counts[cohort])
    floor = pool[min(top, len(pool))-1]['opportunity_score']-quality_band if modern and pool else None
    coverage = {}
    if modern:
        for video in pool:
            if video['opportunity_score'] >= floor and video.get('market_cohort') and video.get('production_fit') != 'POOR':
                coverage.setdefault(video['market_cohort'], video)
    chosen = list(coverage.values())[:top]
    for video in chosen:
        video.update(selection_phase='COHORT_COVERAGE', selection_reason=f'Strongest qualifying cohort opportunity; score >= global cutoff minus {quality_band:g} ({floor:.3f})')
    selected_ids = {v['video_id'] for v in chosen}
    for video in pool:
        if len(chosen) >= top: break
        if video['video_id'] not in selected_ids:
            video.update(selection_phase='GLOBAL_FILL', selection_reason='Remaining slot filled in unchanged global quality ordering')
            chosen.append(video)
    return {'radar_run_id': run['run_id'], 'metadata': metadata, 'created_at': run['created_at'],
            'source_observed_at': run['observed_at'], 'candidates': chosen, 'failures': failures}
