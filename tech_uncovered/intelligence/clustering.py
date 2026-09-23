import re
from collections import Counter
from statistics import median
from .models import stable_id
from ..settings import parse_time


def normalize(value, config):
    value = re.sub(r'\s+', ' ', (value or '').casefold()).strip()
    for alias, canonical in sorted(config.get('entity_aliases', {}).items(), key=lambda p: -len(p[0])):
        value = re.sub(r'\b' + re.escape(alias) + r'\b', canonical, value)
    return value


def event_identity(brief, config):
    from .opportunities import metadata_identity
    identity = metadata_identity(brief)
    if identity:
        return identity
    if 'CONTEXT_LIMITED' in brief.flags:
        return ('singleton', brief.video_id)
    if brief.event_key:
        return ('explicit_event', normalize(brief.event_key, config))
    if brief.evergreen_or_news == 'evergreen' and brief.mechanism_question:
        return ('evergreen', normalize(brief.canonical_subject, config), normalize(brief.mechanism_question, config))
    if brief.products_models and brief.event_type:
        return ('product_event', tuple(sorted(normalize(p, config) for p in brief.products_models)),
                normalize(brief.event_type, config))
    return ('singleton', brief.video_id)


def cluster_stories(briefs, candidates, config, now):
    lookup = {c['video_id']: c for c in candidates}
    groups = []
    for brief in sorted(briefs, key=lambda b: b.video_id):
        identity = event_identity(brief, config)
        for key, members in groups:
            if key != identity:
                continue
            if all(brief.evergreen_or_news == b.evergreen_or_news == 'evergreen' or
                   abs((parse_time(lookup[brief.video_id]['published_at']) -
                        parse_time(lookup[b.video_id]['published_at'])).total_seconds()) / 86400 <= config['cluster_window_days']
                   for b in members):
                members.append(brief)
                break
        else:
            groups.append((identity, [brief]))
    clusters = []
    for identity, members in groups:
        videos = [lookup[b.video_id] for b in members]
        channel_ids = sorted({v['channel_id'] for v in videos})
        scores = [v['velocity_adjusted_score'] for v in videos]
        angles = Counter(b.competitor_angle for b in members if b.competitor_angle != 'unknown')
        saturated = 100 * max(angles.values()) / len(members) * min((len(channel_ids)-1)/3, 1) if angles else 50
        ages = [max(0, (now - parse_time(v['published_at'])).total_seconds()/86400) for v in videos]
        representative = min(members, key=lambda b: (len(b.canonical_subject or ''), b.video_id))
        topic = representative.canonical_subject or 'Unresolved subject — context required'
        clusters.append({'cluster_id': stable_id('trend', [identity, sorted(b.video_id for b in members)]),
                         'canonical_topic': topic, 'supporting_video_ids': sorted(b.video_id for b in members),
                         'supporting_channels': sorted({v['channel'] for v in videos}),
                         'independent_channel_count': len({v['channel_id'] for v in videos if v.get('source_role') != 'vendor_official'}),
                         'vendor_channel_count': len({v['channel_id'] for v in videos if v.get('source_role') == 'vendor_official'}),
                         'radar_cross_cohort_support': max((v.get('cross_cohort_support') or 0 for v in videos), default=0),
                         'supporting_channel_ids': channel_ids, 'number_of_distinct_channels': len(channel_ids),
                         'median_outlier_score': median(scores), 'max_velocity_score': max(scores),
                         'median_raw_outlier_ratio': median(v['outlier_ratio'] for v in videos),
                         'recency': {'median_age_days': median(ages), 'as_of': now.isoformat()},
                         'story_summary': members[0].core_event or 'Underlying event has not been established.',
                         'story_summary_type': 'INFERENCE', 'repeated_angles': sorted(a for a,n in angles.items() if n > 1),
                         'observed_angles': sorted(angles),
                         'missing_angles': sorted(set(['mechanism', 'practical example', 'comparison', 'implications']) - set(angles)),
                         'saturation_level': 'HIGH' if saturated >= 65 else 'MEDIUM' if saturated >= 35 else 'LOW',
                         'saturation_score': saturated, 'saturation_uncertain': not bool(angles),
                         'match_basis': list(identity),
                         'opportunity_notes': 'Missing angles are unobserved in this sample, not established market gaps. Channel breadth is not independent factual corroboration.'})
    return sorted(clusters, key=lambda c: (-c['number_of_distinct_channels'], -c['median_outlier_score'], c['cluster_id']))
