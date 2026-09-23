import math
import re
from statistics import median
from ..settings import parse_time

COMPONENTS = ('DemandSignal', 'Freshness', 'Originality', 'AudienceFit', 'ProductionFit',
              'EvidenceQuality', 'Expandability', 'SaturationRisk')


def validate_config(config):
    weights = config.get('weights', {})
    if set(weights) != set(COMPONENTS) or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError('Weights must define all eight components with finite nonnegative values')
    if not math.isclose(sum(weights.values()), 1, abs_tol=1e-9):
        raise ValueError('Weights must sum to 1')
    for key in ('evidence_threshold', 'originality_threshold', 'recommendation_threshold', 'similarity_review', 'similarity_reject'):
        if not isinstance(config.get(key), (int, float)) or not 0 <= config[key] <= 100:
            raise ValueError(f'{key} must be between 0 and 100')
    if config['similarity_review'] >= config['similarity_reject']:
        raise ValueError('Similarity review threshold must be below rejection threshold')
    if config['cluster_window_days'] <= 0 or config['stale_news_days'] <= 0:
        raise ValueError('Time windows must be positive')
    threshold = config.get('researchability_threshold', 60)
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 100:
        raise ValueError('researchability_threshold must be between 0 and 100')
    if not isinstance(config.get('intake_limit', 30), int) or isinstance(config.get('intake_limit', 30), bool) or config.get('intake_limit', 30) < 1:
        raise ValueError('Invalid intake limit')
    for key in ('intake_quality_band', 'preview_score_window'):
        value = config.get(key, 7)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('Invalid editorial selection band: '+key)
    return config


def weighted_score(components, weights):
    return sum(weights[k] * (100 - components[k] if k == 'SaturationRisk' else components[k]) for k in COMPONENTS)


def apply_readiness(idea, config):
    from .entry_contract import apply
    apply(idea)
    factual_flags = {'FACTUAL_REVIEW_REQUIRED', 'RESEARCH_REQUIRED', 'CONTEXT_LIMITED', 'PROVIDER_FAILURE'}
    originality_flags = {'REJECT_NEAR_DUPLICATE', 'EDITORIAL_REVIEW_REQUIRED', 'ORIGINALITY_CONTEXT_LIMITED'}
    other_review = any(flag.endswith('REVIEW_REQUIRED') or flag.startswith(('FACTUAL_', 'ORIGINALITY_')) for flag in idea.risk_flags)
    idea.production_ready = bool(
        not other_review and not (set(idea.risk_flags) & (factual_flags | originality_flags))
        and idea.scores['EvidenceQuality'] >= config['evidence_threshold']
        and not idea.required_research and idea.similarity_status == 'CLEAR')
    if idea.duplicate_of or idea.similarity_status in {'REVIEW', 'REJECT'} or set(idea.risk_flags) & (originality_flags | {'FACTUAL_REVIEW_REQUIRED'}):
        idea.category = 'REJECTED / REVIEW REQUIRED'
    elif idea.production_ready:
        idea.category = 'READY FOR SCRIPTING'
    elif not idea.story_requirement_satisfied:
        idea.category = 'BACKLOG'
    elif (idea.source_opportunities and idea.canonical_subject
          and idea.idea_researchability_score >= config.get('researchability_threshold', 60)
          and all(s.get('production_fit') != 'POOR' for s in idea.source_opportunities)
          and idea.similarity_status == 'CLEAR' and not {'STALE_NEWS', 'AMBIGUOUS_STORY'} & set(idea.risk_flags)):
        idea.category = 'RECOMMENDED FOR RESEARCH'
    elif not idea.source_opportunities and idea.idea_score >= config['recommendation_threshold'] and 'STALE_NEWS' not in idea.risk_flags:
        idea.category = 'RECOMMENDED FOR RESEARCH'
    else:
        idea.category = 'BACKLOG'


def score_idea(idea, cluster, briefs, candidates, config, now):
    relevant = [b for b in briefs if b.video_id in idea.source_video_ids]
    source_lookup = {v['video_id']: v for v in candidates}
    claims = {}
    for b in relevant:
        for claim in b.factual_claims + b.uncertain_claims:
            if claim.get('material', True):
                key = claim['claim_id']
                # Conflicting assessments cannot be improved through duplication.
                if key not in claims or claim['status'] != 'VERIFIED':
                    claims[key] = claim
    signal = 100 * min(math.log2(1 + max(0, cluster['median_outlier_score'])) / math.log2(9), 1)
    breadth = {1: 25, 2: 60, 3: 80}.get(cluster['number_of_distinct_channels'], 100)
    recency = 100 * 2 ** (-cluster['recency']['median_age_days'] / 30)
    freshness, stale, date_bases = [], False, []
    for brief in relevant:
        if brief.evergreen_or_news == 'evergreen':
            freshness.append(80)
            date_bases.append('evergreen')
        elif brief.evergreen_or_news == 'news':
            # Event date is only accepted for freshness when a verified claim explicitly supports it.
            date_verified = bool(brief.event_date and any(c['status'] == 'VERIFIED' and c.get('supports_event_date') == brief.event_date
                                                        for c in brief.factual_claims))
            date = brief.event_date if date_verified else source_lookup[brief.video_id]['published_at']
            if len(date) == 10:
                date += 'T00:00:00+00:00'
            age = (now - parse_time(date)).total_seconds()/86400
            if age < 0:
                freshness.append(40)
                idea.risk_flags.append('FACTUAL_REVIEW_REQUIRED')
                idea.required_research.append('Resolve the future-dated event or publication timestamp.')
            else:
                value = 100 * 2 ** (-age / 14)
                freshness.append(value if date_verified else min(value, 60))
                stale |= age > config['stale_news_days']
            date_bases.append('verified_event_date' if date_verified else 'publication_date_proxy')
        else:
            freshness.append(40)
            date_bases.append('unknown')
    values = {'VERIFIED': 100, 'PARTIALLY_VERIFIED': 50, 'UNVERIFIED': 0, 'DISPUTED': 0}
    evidence = sum(values[c['status']] for c in claims.values()) / len(claims) if claims else 0
    topic_text = ' '.join([idea.topic] + [t for b in relevant for t in b.technologies])
    def has(terms):
        return any(re.search(r'\b' + re.escape(t) + r'\b', topic_text, re.I) for t in terms)
    audience = 100 if has(config['primary_terms']) else 60 if has(config['adjacent_terms']) else 30
    if any(b.audience_relevance == 'unrelated' for b in relevant):
        audience = 0
    checks = ('single_question', 'single_mechanism_or_example', 'at_most_three_material_claims', 'achievable_diagrams_or_screens', 'no_bespoke_footage')
    production = 20 * sum(idea.production_assumptions.get(k) is True for k in checks)
    expandability = 25 * len(set(idea.expansion_sections) & {'mechanism', 'comparison', 'application', 'limitations/history'})
    originality = 100 - idea.similarity_details.get('similarity', 100)
    idea.scores = {'DemandSignal': .50*signal + .30*breadth + .20*recency,
                   'Freshness': median(freshness) if freshness else 40, 'Originality': originality,
                   'AudienceFit': audience, 'ProductionFit': production, 'EvidenceQuality': evidence,
                   'Expandability': expandability, 'SaturationRisk': cluster['saturation_score']}
    idea.idea_score = weighted_score(idea.scores, config['weights'])
    if evidence < config['evidence_threshold'] or any(c['status'] != 'VERIFIED' for c in claims.values()) or not claims or idea.required_research:
        idea.risk_flags.append('RESEARCH_REQUIRED')
    if any(c['status'] == 'DISPUTED' for c in claims.values()):
        idea.risk_flags.append('FACTUAL_REVIEW_REQUIRED')
    if originality < config['originality_threshold'] or idea.similarity_status == 'REJECT':
        idea.risk_flags.append('REJECT_NEAR_DUPLICATE')
    if idea.similarity_status == 'REVIEW':
        idea.risk_flags.append('EDITORIAL_REVIEW_REQUIRED')
    if any('CONTEXT_LIMITED' in b.flags for b in relevant):
        idea.risk_flags.append('CONTEXT_LIMITED')
        if not idea.source_opportunities:
            idea.risk_flags.append('ORIGINALITY_CONTEXT_LIMITED')
    if stale:
        idea.risk_flags.append('STALE_NEWS')
    idea.risk_flags = sorted(set(idea.risk_flags))
    idea.required_research = sorted(set(idea.required_research))
    idea.score_rationale = {'radar_strength': signal, 'channel_breadth': breadth, 'recency': recency,
                            'freshness_date_bases': date_bases, 'material_claim_count': len(claims),
                            'claim_statuses': {k: v['status'] for k,v in claims.items()},
                            'production_checks': idea.production_assumptions,
                            'weights': config['weights'], 'scoring_version': '1.0',
                            'note': 'Editorial heuristic, not viral probability; readiness is a separate gate.'}
    apply_readiness(idea, config)
    idea.review_status = idea.category.replace(" / ", "_").replace(" ", "_")
    return idea
