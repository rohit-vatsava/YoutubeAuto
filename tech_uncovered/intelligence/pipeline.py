from dataclasses import asdict
from datetime import timedelta
from ..settings import parse_time
from copy import deepcopy
import uuid

from . import SCHEMA_VERSION, SCORING_VERSION
from .clustering import cluster_stories
from .extraction import extract, ground
from .generation import DeterministicIdeaGenerator
from .models import digest, TranscriptResult
from .providers import (TranscriptProvider, ResearchProvider, IdeaGenerator, SimilarityChecker,
                        UnavailableTranscriptProvider, NoOpResearchProvider)
from .scoring import score_idea, validate_config
from .selection import select_candidates
from .similarity import DeterministicSimilarityChecker, consolidate, references_for
from .storage import persist


def run_intelligence(db, config, now, *, radar_run_id=None, top=None, offline=True, refresh=False,
                     transcript_provider: TranscriptProvider | None = None,
                     research_provider: ResearchProvider | None = None,
                     generator: IdeaGenerator | None = None,
                     similarity_checker: SimilarityChecker | None = None):
    validate_config(config)
    top = config.get("intake_limit", 30) if top is None else top
    selected = select_candidates(db, radar_run_id, top, config.get("selection_order"), quality_band=config.get("intake_quality_band", 7))
    candidates = deepcopy(selected['candidates'])
    if selected['metadata'].get('mode') != 'synthetic' and any(
            now - parse_time(v['observed_at']) >= timedelta(days=30) for v in candidates):
        raise ValueError('Selected Radar observations have expired; collect a fresh Radar run. No other run was substituted.')
    run_id = str(uuid.uuid4())
    transcript_provider = transcript_provider or UnavailableTranscriptProvider()
    research_provider = research_provider or NoOpResearchProvider()
    generator = generator or DeterministicIdeaGenerator()
    checker = similarity_checker or DeterministicSimilarityChecker(config)
    providers = {role: {'name': p.name, 'version': p.version}
                 for role,p in [('transcript',transcript_provider),('research',research_provider),
                                ('generator',generator),('similarity',checker)]}
    failures = list(selected['failures'])
    warnings = []
    if selected['metadata'].get('status') != 'complete':
        warnings.append('The explicitly selected Radar run is partial; its failures remain in radar_metadata.')
    transcripts, briefs = {}, []
    for candidate in candidates:
        vid = candidate['video_id']
        provider_failed = False
        try:
            transcript = transcript_provider.retrieve(deepcopy(candidate), offline=offline, refresh=refresh, now=now.isoformat())
            if transcript.transcript_status not in {'AVAILABLE','UNAVAILABLE','ERROR'}:
                raise ValueError('Invalid transcript status')
        except Exception as exc:
            failures.append({'stage':'transcript','video_id':vid,'reason':type(exc).__name__ + ': provider failed; metadata fallback'})
            transcript = TranscriptResult(transcript_status='ERROR', retrieved_at=now.isoformat(),
                                          reason='Provider failed; no transcript invented', provider_name=transcript_provider.name,
                                          provider_version=transcript_provider.version, content_hash=digest(['error',vid]))
            provider_failed = True
        transcripts[vid] = asdict(transcript)
        try:
            brief = extract(candidate, transcript, config)
        except Exception as exc:
            failures.append({'stage':'extraction','video_id':vid,'reason':type(exc).__name__ + ': invalid context; metadata fallback'})
            brief = extract(candidate, TranscriptResult(), config)
            provider_failed = True
        brief.radar_run_id, brief.intelligence_run_id = selected['radar_run_id'], run_id
        brief.provider_versions = providers
        try:
            evidence = research_provider.research(deepcopy(brief), offline=offline, refresh=refresh, now=now.isoformat())
            brief = ground(brief, evidence)
        except Exception as exc:
            failures.append({'stage':'research','video_id':vid,'reason':type(exc).__name__ + ': research unavailable'})
            provider_failed = True
        if provider_failed:
            brief.flags.append('PROVIDER_FAILURE')
        briefs.append(brief)
    # A shared claim ID must never collapse different factual propositions.
    claim_texts = {}
    for brief in briefs:
        for claim in brief.factual_claims + brief.uncertain_claims:
            claim_texts.setdefault(claim['claim_id'], set()).add(claim['text'])
    conflicting = {cid for cid, texts in claim_texts.items() if len(texts) > 1}
    if conflicting:
        for brief in briefs:
            for claim in list(brief.factual_claims):
                if claim['claim_id'] in conflicting:
                    brief.factual_claims.remove(claim)
                    brief.uncertain_claims.append(claim)
            for claim in brief.uncertain_claims:
                if claim['claim_id'] in conflicting:
                    claim.update(status='UNVERIFIED', statement_type='UNVERIFIED_CLAIM', evidence_ids=[])
                    brief.flags.append('FACTUAL_REVIEW_REQUIRED')
        warnings.append('Conflicting claim IDs were downgraded to unverified and flagged for factual review.')
    clusters = cluster_stories(briefs, candidates, config, now)
    cluster_lookup = {v:c for c in clusters for v in c['supporting_video_ids']}
    ideas = []
    for brief in briefs:
        try:
            generated = generator.generate(deepcopy(brief), deepcopy(cluster_lookup[brief.video_id]))
            if not 0 <= len(generated) <= 5:
                raise ValueError('Generator must return at most five ideas')
            for idea in generated:
                idea.risk_flags = sorted(set(idea.risk_flags + brief.flags))
                if idea.source_video_ids != [brief.video_id] or not idea.idea_id:
                    raise ValueError('Generator returned invalid source lineage')
            ideas.extend(generated)
            if not generated:
                warnings.append(f'{brief.video_id}: insufficient subject context to generate specific ideas')
        except Exception as exc:
            failures.append({'stage':'generation','video_id':brief.video_id,'reason':type(exc).__name__ + ': idea generation failed'})
    consolidate(ideas)
    references = references_for(briefs, candidates)
    clusters_by_id = {c['cluster_id']: c for c in clusters}
    scored = []
    for idea in sorted(ideas, key=lambda i: (i.duplicate_of is not None, i.idea_id)):
        try:
            if idea.duplicate_of:
                idea.similarity_details = {'similarity':100.0,'status':'REJECT','reference':idea.duplicate_of,'reason':'Consolidated duplicate direction within trend'}
            else:
                idea.similarity_details = checker.check(idea, deepcopy(references))
            idea.similarity_status = idea.similarity_details['status']
            if idea.similarity_status not in {'CLEAR','REVIEW','REJECT'}:
                raise ValueError('Invalid similarity status')
            similarity = idea.similarity_details['similarity']
            if not isinstance(similarity,(int,float)) or not 0 <= similarity <= 100:
                raise ValueError('Invalid similarity score')
            idea.radar_run_id, idea.intelligence_run_id = selected['radar_run_id'], run_id
            idea.provider_versions = providers
            idea.story_context = [b.to_dict() for b in briefs if b.video_id in idea.source_video_ids]
            from .opportunities import enrich_idea
            enrich_idea(idea, candidates)
            score_idea(idea, clusters_by_id[idea.cluster_id], briefs, candidates, config, now)
            scored.append(idea)
            if not idea.duplicate_of:
                references.append({'id':idea.idea_id,'generated':True,'topic':idea.topic,'transformation':idea.transformation,
                                   'audience_question':idea.audience_question,
                                   'texts':[idea.one_sentence_premise,idea.audience_question]})
        except Exception as exc:
            failures.append({'stage':'idea_scoring','video_id':','.join(idea.source_video_ids),'reason':type(exc).__name__ + ': idea skipped'})
    scored.sort(key=lambda i: (-i.idea_score, i.idea_id))
    rank = 0
    for idea in scored:
        if idea.category != 'REJECTED / REVIEW REQUIRED':
            rank += 1
            idea.rank = rank
    mode = 'synthetic' if selected['metadata'].get('mode') == 'synthetic' else ('offline' if offline else 'local')
    metadata = {'mode':mode,'status':'partial' if failures else 'complete','offline':offline,
                'provider_versions':providers, 'config':config,'config_hash':digest(config),
                'radar_metadata':selected['metadata'], 'radar_created_at':selected['created_at'],
                'refresh_context':refresh,'candidates_analyzed':len(briefs),'partial_failures':failures,
                'warnings':warnings,'api_requests':0,
                'quality_version':'2.2',
                'note':'Deterministic editorial heuristics; no causal performance or viral-probability claims.'}
    result = {'schema_version':SCHEMA_VERSION,'module':'Intelligence','scoring_version':SCORING_VERSION,
              'intelligence_run_id':run_id,'radar_run_id':selected['radar_run_id'],'generated_at':now.isoformat(),
              'metadata':metadata,'candidates':candidates,'transcripts':transcripts,
              'story_briefs':[b.to_dict() for b in briefs],'trend_clusters':clusters,
              'ideas':[i.to_dict() for i in scored]}
    # Persist default preview explanations on new immutable M2 snapshots.
    from .editorial import story_fields, researchability_fields, eligible, story_first
    from ..scripting.resolution import assess_researchability
    choices = []
    for idea in result['ideas']:
        idea.update(story_fields(idea, clusters_by_id[idea['cluster_id']]))
        assessment = assess_researchability({'idea': idea, 'competitor_references': []})
        idea.update(researchability_fields(idea, assessment['researchability_score']))
        idea.update(topic_rank=None, angle_rank_within_topic=None, preview_selection_phase=None)
        if eligible(idea):
            choices.append({'idea': idea, **story_fields(idea), **researchability_fields(idea, assessment['researchability_score'])})
    story_first(choices, 10, config.get('preview_score_window', 7))
    for choice in choices:
        choice['idea'].update({k: choice.get(k) for k in ('topic_rank', 'angle_rank_within_topic', 'preview_selection_phase')})
    result['metadata']['editorial_selection_version'] = 'cohort-story-v1'
    persist(db,result)
    return result
