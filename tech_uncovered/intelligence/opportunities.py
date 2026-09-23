"""Offline Radar hints are research leads, never verified claims."""
import re
from copy import deepcopy

BROAD = {'ai', 'hardware', 'software', 'technology', 'computing', 'model', 'gpu', 'chip'}
FIELDS = ('market_cohort opportunity_score normalized_radar_signal researchability_score '
          'researchability_reasons named_entity_hints event_hints production_fit production_fit_reason '
          'commercial_value_tag cross_cohort_support source_role title channel video_id published_at '
          'duration_seconds velocity_adjusted_score canonical_topics radar_run_id snapshot_hash').split()


def concrete(subject):
    return bool(subject and subject.casefold().strip() not in BROAD)


def seed(brief, candidate):
    if 'named_entity_hints' not in candidate:
        return
    brief.source_opportunity = {k: deepcopy(candidate[k]) for k in FIELDS if k in candidate}
    from .subject_resolution import MetadataSubjectResolver
    resolved = MetadataSubjectResolver().resolve(candidate)
    brief.metadata_subject_resolution = resolved
    brief.story_context_status = resolved['story_context_status']
    brief.story_type = resolved['story_type']
    brief.canonical_subject = resolved['canonical_subject']
    brief.entities = brief.named_entities = resolved['named_entities']
    brief.products_models = resolved['product_or_project']
    brief.technologies = resolved['technologies']
    brief.alleged_event = brief.core_event = resolved['event_or_change']
    brief.evergreen_or_news = 'evergreen' if brief.story_type == 'EVERGREEN_TOPIC' else 'news' if brief.story_type == 'EVENT_STORY' else 'unknown'
    if brief.story_context_status == 'INSUFFICIENT_CONTEXT':
        brief.flags.append('INSUFFICIENT_CONTEXT')
    if any('Multiple developments' in r for r in resolved['unresolved_reasons']):
        brief.flags.append('AMBIGUOUS_STORY')
    brief.unknown_reasons['metadata_subject_resolution'] = '; '.join(resolved['unresolved_reasons'])
    for name in ('canonical_subject', 'entities', 'named_entities', 'technologies', 'products_models', 'core_event', 'alleged_event', 'evergreen_or_news'):
        brief.field_provenance[name] = {'type': 'INFERENCE', 'basis': resolved['extraction_method'],
            'resolver_version': resolved['resolver_version'], 'video_id': candidate['video_id'],
            'snapshot_hash': candidate.get('snapshot_hash'), 'note': 'Title-derived research lead; not factual evidence'}


def metadata_identity(brief):
    if 'AMBIGUOUS_STORY' in brief.flags or brief.story_context_status == 'INSUFFICIENT_CONTEXT':
        return None
    if brief.story_type == 'EVERGREEN_TOPIC':
        return ('metadata_evergreen', tuple(sorted(x.casefold() for x in brief.products_models)) if brief.products_models else brief.canonical_subject.casefold())
    source = brief.source_opportunity
    keys = sorted(k for k in source.get('canonical_topics', []) if k.startswith(('identifier:', 'product:')))
    # Multiple identifiers define a comparison/roundup, not a single-product story.
    if keys and concrete(brief.canonical_subject):
        return ('radar_subject', tuple(keys), (brief.alleged_event,) if brief.metadata_subject_resolution and brief.alleged_event else tuple(sorted(source.get('event_hints', []))))
    if brief.products_models:
        return ('radar_product', tuple(sorted(x.casefold() for x in brief.products_models)), brief.alleged_event)
    if concrete(brief.canonical_subject) and brief.alleged_event:
        return ('radar_event', brief.canonical_subject.casefold(), brief.alleged_event.casefold())
    return None


def enrich_idea(idea, candidates):
    sources = [c for c in candidates if c['video_id'] in idea.source_video_ids and 'named_entity_hints' in c]
    if not sources:
        return
    if idea.story_context:
        idea.named_entities = sorted({e for b in idea.story_context for e in (b.get('named_entities') or b.get('entities', []))})
    idea.source_opportunities = [{k: deepcopy(c[k]) for k in FIELDS if k in c} for c in sources]
    values = [c['researchability_score'] for c in sources if c.get('researchability_score') is not None]
    idea.source_researchability_score = max(values) if values else None
    ambiguity = 25 if 'AMBIGUOUS_STORY' in idea.risk_flags else 15 if len(idea.named_entities) > 4 else 0
    idea.idea_researchability_score = round(max(0, min(100,
        .5 * (idea.source_researchability_score or 0) + 20 * concrete(idea.canonical_subject)
        + 5 * min(len(idea.named_entities), 3) + 15 * bool(idea.alleged_event) - ambiguity)), 2)
