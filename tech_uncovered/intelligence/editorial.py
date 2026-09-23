"""Score-preserving editorial eligibility and story-first selection."""
import math
import re
from collections import defaultdict
from .models import stable_id


def state(value):
    return re.sub(r'[^A-Z0-9]+', '_', str(value or '').upper()).strip('_')


def eligible(idea, *, include_backlog=False):
    states = {state(idea.get(k)) for k in ('category', 'review_status', 'status')}
    if any('REJECT' in s or 'REVIEW_REQUIRED' in s for s in states):
        return False
    if idea.get('duplicate_of') or idea.get('similarity_status') in {'REVIEW', 'REJECT'}:
        return False
    if set(idea.get('risk_flags', [])) & {'REJECT_NEAR_DUPLICATE', 'EDITORIAL_REVIEW_REQUIRED', 'FACTUAL_REVIEW_REQUIRED', 'ORIGINALITY_CONTEXT_LIMITED'}:
        return False
    allowed = {'RECOMMENDED_FOR_RESEARCH', 'READY_FOR_SCRIPTING'}
    if include_backlog:
        allowed.add('BACKLOG')
    if state(idea.get('category')) not in allowed:return False
    from .entry_contract import assess
    return include_backlog or assess(idea)['m3_entry_ready']


def story_fields(idea, cluster=None):
    # Reuse the cluster's subject/event + temporal grouping. Never merge by a
    # company/topic label alone: different events can have the same label.
    cluster = cluster or {}
    identity = cluster.get('cluster_id') or idea.get('cluster_id')
    if not identity:
        identity = ['unresolved', idea.get('idea_id')]
    return {'canonical_story_id': stable_id('story', identity),
            'canonical_story_label': cluster.get('canonical_topic') or idea.get('canonical_subject') or idea['topic'],
            'angle_type': idea.get('transformation') or idea.get('proposed_angle')}


def researchability_fields(idea, preview_score):
    return {'m2_researchability_score': idea.get('m2_researchability_score') if idea.get('m2_researchability_score') is not None else idea.get('idea_researchability_score'),
            'm2_researchability_version': 'radar-context-v1',
            'preview_researchability_score': preview_score,
            'preview_researchability_version': 'context-resolvability-v1'}


def story_first(choices, top=10, score_window=7):
    if not isinstance(score_window, (int, float)) or not math.isfinite(score_window) or score_window < 0:
        raise ValueError('Invalid editorial score window')
    groups = defaultdict(list)
    for c in choices:
        groups[c['canonical_story_id']].append(c)
    for group in groups.values():
        # Best angle retains the existing bounded researchability tie-break.
        remaining = list(group)
        group.clear()
        while remaining:
            ceiling = max(c['idea']['idea_score'] for c in remaining)
            band = [c for c in remaining if c['idea']['idea_score'] >= ceiling-score_window]
            winner = min(band, key=lambda c: (-c['preview_researchability_score'], -c['idea']['idea_score'], c['idea']['idea_id']))
            group.append(winner)
            remaining.remove(winner)
        for n, c in enumerate(group, 1):
            c['angle_rank_within_topic'] = n
    selected, covered, ranks = [], set(), {}
    def cohorts(c):
        return {s['market_cohort'] for s in c['idea'].get('source_opportunities', []) if s.get('market_cohort')}
    def take(pool, phase):
        while pool and len(selected) < top:
            ceiling = max(c['idea']['idea_score'] for c in pool)
            band = [c for c in pool if c['idea']['idea_score'] >= ceiling-score_window]
            diverse = [c for c in band if cohorts(c)-covered]
            winner = min(diverse or band, key=lambda c: (-c['preview_researchability_score'], -c['idea']['idea_score'], c['idea']['idea_id']))
            sid = winner['canonical_story_id']
            ranks.setdefault(sid, len(ranks)+1)
            winner.update(topic_rank=ranks[sid], preview_selection_phase=phase,
                          selection_reason=f'{phase}; {"unrepresented cohort preferred within" if diverse else "researchability tie-break within"} {score_window:g}-point idea-score band; scores unchanged')
            selected.append(winner); covered.update(cohorts(winner)); pool.remove(winner)
    take([g[0] for g in groups.values()], 'STORY_FIRST')
    take([g[1] for g in groups.values() if len(g)>1 and g[0] in selected], 'SECONDARY_ANGLE_FILL')
    return selected
