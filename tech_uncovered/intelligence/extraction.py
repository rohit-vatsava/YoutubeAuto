"""Conservative extraction: supplied context is not automatically factual evidence."""
import re
from .models import StoryBrief, stable_id

ANGLES = ('comparison', 'breakthrough', 'conflict', 'surprise', 'failure', 'what changed',
          'why this matters', 'demonstration', 'controversy', 'prediction', 'tutorial', 'myth correction')


def extract(candidate, transcript, config):
    brief = StoryBrief(video_id=candidate['video_id'])
    from .opportunities import FIELDS
    from copy import deepcopy
    brief.source_opportunity = {k: deepcopy(candidate[k]) for k in FIELDS if k in candidate} if 'named_entity_hints' in candidate else {}
    context = transcript.structured_context
    supplied_fields = ('canonical_subject', 'core_event', 'what_changed', 'why_now', 'audience_relevance',
                       'competitor_angle', 'hook_pattern', 'emotional_frame', 'novelty_type',
                       'evergreen_or_news', 'time_sensitivity', 'content_depth', 'context_summary',
                       'event_key', 'event_type', 'event_date', 'mechanism_question')
    for name in supplied_fields:
        value = context.get(name)
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f'{name} must be text')
            setattr(brief, name, value)
            brief.field_provenance[name] = {'type': 'INFERENCE', 'basis': 'supplied_context'}
    for name in ('entities', 'technologies', 'companies', 'people', 'products_models'):
        values = context.get(name, [])
        if not isinstance(values, list) or any(not isinstance(x, str) for x in values):
            raise ValueError(f'{name} must be a list of strings')
        setattr(brief, name, sorted(set(values)))
    if brief.evergreen_or_news not in {'news', 'evergreen', 'unknown'}:
        raise ValueError('evergreen_or_news must be news, evergreen, or unknown')
    if brief.competitor_angle not in ANGLES + ('unknown',):
        brief.competitor_angle = 'unknown'
    if not context:
        brief.flags.append('CONTEXT_LIMITED')
        # Even a raw transcript is not fully understood by this deterministic extractor.
        if transcript.transcript_status == 'AVAILABLE':
            brief.flags.append('TRANSCRIPT_REQUIRES_CONTEXT_REVIEW')
        title = candidate['title']
        entities = sorted({term for term in config['primary_terms']
                           if re.search(r'\b' + re.escape(term) + r'\b', title, re.I)})
        brief.entities = entities
        brief.canonical_subject = ', '.join(entities) or None
        brief.field_provenance['canonical_subject'] = {'type': 'INFERENCE', 'basis': 'title_terms_only'}
        for pattern, angle in [(r'\bvs\.?\b|\bversus\b', 'comparison'), (r'\bhow to\b', 'tutorial'),
                               (r'\bfail\w*\b', 'failure'), (r'\bnew\b|\brelease\w*\b', 'what changed')]:
            if re.search(pattern, title, re.I):
                brief.competitor_angle = angle
                break
        brief.hook_pattern = 'question' if '?' in title else ('comparison' if brief.competitor_angle == 'comparison' else 'unknown')
        brief.field_provenance['competitor_angle'] = {'type': 'INFERENCE', 'basis': 'title_pattern_not_causal'}
    if not context:
        from .opportunities import seed
        seed(brief, candidate)
    claims = context.get('claims', [])
    if not isinstance(claims, list):
        raise ValueError('claims must be a list')
    if not claims:
        claims = [{'claim_id': stable_id('claim', [brief.video_id, candidate['title']]),
                   'text': ('Validate the underlying concept and educational framing represented by this video.' if brief.story_type == 'EVERGREEN_TOPIC' else 'Validate the underlying subject and development represented by this video.'),
                   'material': True, 'assessment_question': True}]
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get('text'), str):
            raise ValueError('Invalid factual claim')
        brief.uncertain_claims.append({**claim, 'claim_id': claim.get('claim_id') or stable_id('claim', claim['text']),
                                      'material': claim.get('material', True), 'status': 'UNVERIFIED',
                                      'statement_type': 'UNVERIFIED_CLAIM', 'evidence_ids': [],
                                      'origin': 'supplied_context' if context else 'metadata_research_question'})
    brief.source_evidence = [{'evidence_id': 'video:' + brief.video_id, 'reference': candidate['url'],
                              'source_type': 'COMPETITOR', 'statement_type': 'OBSERVATION',
                              'note': 'Evidence of competitor framing; not independent factual verification'}]
    for name in ('canonical_subject', 'core_event', 'what_changed', 'why_now', 'event_date'):
        if not getattr(brief, name):
            brief.unknown_reasons[name] = 'Not established by available context'
    if not brief.canonical_subject or not brief.core_event or not brief.context_summary:
        if 'CONTEXT_LIMITED' not in brief.flags:
            brief.flags.append('CONTEXT_LIMITED')
    brief.confidence = 0.6 if 'CONTEXT_LIMITED' not in brief.flags else 0.2
    return brief


def ground(brief, research):
    valid_statuses = {'VERIFIED','PARTIALLY_VERIFIED','UNVERIFIED','DISPUTED'}
    if any(a.get('status', 'UNVERIFIED') not in valid_statuses for a in research.assessments.values()):
        raise ValueError('Research provider returned invalid verification status')
    evidence_ids = {e['evidence_id'] for e in research.sources}
    if any(set(a.get('evidence_ids', [])) - evidence_ids for a in research.assessments.values()):
        raise ValueError('Research assessment references missing evidence')
    brief.source_evidence.extend({**e, 'retrieved_at': research.retrieved_at,
                                  'provider_name': research.provider_name, 'provider_version': research.provider_version}
                                 for e in research.sources)
    claims = brief.factual_claims + brief.uncertain_claims
    brief.factual_claims, brief.uncertain_claims = [], []
    for claim in claims:
        assessment = research.assessments.get(claim['claim_id'], {})
        status = assessment.get('status', 'UNVERIFIED')
        if status != 'UNVERIFIED' and (not assessment.get('evidence_ids') or not assessment.get('rationale')):
            status = 'UNVERIFIED'
        claim = {**claim, 'status': status, 'evidence_ids': assessment.get('evidence_ids', []),
                 'verification_rationale': assessment.get('rationale', 'No external verification available'),
                 'assessment': assessment}
        # A question cannot become a fact merely by importing a status label.
        if claim.get('assessment_question'):
            claim['status'] = status = 'UNVERIFIED'
        claim['statement_type'] = 'FACT' if status == 'VERIFIED' else 'UNVERIFIED_CLAIM'
        (brief.factual_claims if status == 'VERIFIED' else brief.uncertain_claims).append(claim)
    return brief
