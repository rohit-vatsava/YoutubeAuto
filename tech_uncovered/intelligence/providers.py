"""Provider contracts have no vendor, HTTP, file, or credential assumptions."""
from copy import deepcopy
from typing import Protocol

from .models import ResearchResult, StoryBrief, TranscriptResult, IdeaCandidate, digest


class TranscriptProvider(Protocol):
    name: str
    version: str
    def retrieve(self, candidate: dict, *, offline: bool, refresh: bool, now: str) -> TranscriptResult: ...


class ResearchProvider(Protocol):
    name: str
    version: str
    def research(self, brief: StoryBrief, *, offline: bool, refresh: bool, now: str) -> ResearchResult: ...


class IdeaGenerator(Protocol):
    name: str
    version: str
    def generate(self, brief: StoryBrief, cluster: dict) -> list[IdeaCandidate]: ...


class SimilarityChecker(Protocol):
    name: str
    version: str
    def check(self, idea: IdeaCandidate, references: list[dict]) -> dict: ...


class UnavailableTranscriptProvider:
    name, version = 'unavailable', '1'
    def retrieve(self, candidate, *, offline, refresh, now):
        result = TranscriptResult(retrieved_at=now)
        result.content_hash = digest({'video_id': candidate['video_id'], 'status': 'UNAVAILABLE'})
        return result


class LocalTranscriptProvider:
    name, version = 'local-context', '1'
    def __init__(self, entries):
        self.entries = deepcopy(entries)

    def retrieve(self, candidate, *, offline, refresh, now):
        entry = self.entries.get(candidate['video_id'])
        if entry is None:
            result = UnavailableTranscriptProvider().retrieve(candidate, offline=offline, refresh=refresh, now=now)
            result.provider_name = self.name
            return result
        if not isinstance(entry, dict):
            raise ValueError('Context entry must be an object')
        text, segments = entry.get('text'), entry.get('segments', [])
        if text is not None and not isinstance(text, str):
            raise ValueError('Transcript text must be a string')
        if not isinstance(segments, list):
            raise ValueError('Transcript segments must be a list')
        for segment in segments:
            if (not isinstance(segment, dict) or not isinstance(segment.get('text'), str)
                    or not isinstance(segment.get('start'), (int, float)) or segment['start'] < 0):
                raise ValueError('Invalid transcript segment')
        available = bool((text and text.strip()) or segments)
        if available and not (entry.get('source') and entry.get('provenance_note')):
            raise ValueError('Supplied transcript requires source and provenance_note')
        context = entry.get('context', {})
        if not isinstance(context, dict):
            raise ValueError('Structured context must be an object')
        return TranscriptResult(
            transcript_status='AVAILABLE' if available else 'UNAVAILABLE',
            transcript_source=entry.get('source'), transcript_language=entry.get('language'),
            text=text if available else None, segments=deepcopy(segments), structured_context=deepcopy(context),
            retrieved_at=now, reason=None if available else 'No transcript supplied; structured context may be available',
            provider_name=self.name, provider_version=self.version, content_hash=digest(entry))


class NoOpResearchProvider:
    name, version = 'no-op', '1'
    def research(self, brief, *, offline, refresh, now):
        return ResearchResult(retrieved_at=now)


class ManualResearchProvider:
    name, version = 'manual-evidence', '1'
    def __init__(self, data):
        self.data = deepcopy(data)

    def research(self, brief, *, offline, refresh, now):
        assessments, sources = {}, {}
        supplied = self.data.get('assessments', {})
        catalogue = self.data.get('sources', {})
        for claim in brief.factual_claims + brief.uncertain_claims:
            item = supplied.get(claim['claim_id'])
            if not item:
                continue
            # Mapping to exact claim text prevents reuse of an assessment for a different claim.
            if item.get('claim_text') != claim['text']:
                continue
            ids = item.get('evidence_ids', [])
            status = item.get('status', 'UNVERIFIED')
            if status not in {'VERIFIED', 'PARTIALLY_VERIFIED', 'UNVERIFIED', 'DISPUTED'}:
                raise ValueError('Unknown verification status')
            valid = []
            for evidence_id in ids:
                source = catalogue.get(evidence_id, {})
                if (source.get('reference') and source.get('publisher') and source.get('excerpt')
                        and source.get('source_type') in {'PRIMARY', 'SECONDARY'}
                        and source.get('relation') in {'SUPPORTS', 'CONTRADICTS'}):
                    valid.append(evidence_id)
                    sources[evidence_id] = {**deepcopy(source), 'evidence_id': evidence_id}
            if status != 'UNVERIFIED' and (not valid or not item.get('rationale') or not item.get('assessed_by')):
                status = 'UNVERIFIED'
            if status == 'VERIFIED' and any(sources[i]['relation'] == 'CONTRADICTS' for i in valid):
                status = 'DISPUTED'
            assessments[claim['claim_id']] = {**deepcopy(item), 'status': status, 'evidence_ids': valid,
                                             'verification_basis': 'MANUAL_ASSESSMENT_NOT_AUTOMATED_FACT_CHECK'}
        return ResearchResult(assessments=assessments, sources=list(sources.values()),
                              provider_name=self.name, provider_version=self.version, retrieved_at=now)
