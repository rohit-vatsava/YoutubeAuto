import re
from difflib import SequenceMatcher
from .clustering import normalize

STOP = {'the', 'a', 'an', 'of', 'to', 'and', 'in', 'for', 'with', 'is', 'on', 'this', 'that'}


def normalized(text, config):
    return ' '.join(re.findall(r'\w+', normalize(text, config)))


def content_ngrams(text):
    words = [w for w in text.split() if w not in STOP]
    return {tuple(words[i:i+3]) for i in range(len(words)-2)}


class DeterministicSimilarityChecker:
    name, version = 'lexical-structured', '1'
    def __init__(self, config):
        self.config = config

    def check(self, idea, references):
        best = {'similarity': 0.0, 'reference': None, 'reason': 'No near match detected'}
        for ref in references:
            structural = 0.0
            same_topic = normalized(idea.topic, self.config) == normalized(ref.get('topic', ''), self.config)
            if ref.get('generated') and not same_topic:
                # Known template scaffolding is not distinctive phrasing. Still catch literal duplicates.
                exact = {normalized(x, self.config) for x in ref.get('texts', [])}
                if not any(normalized(x, self.config) in exact for x in (idea.one_sentence_premise, idea.audience_question)):
                    continue
            if (normalized(idea.topic, self.config) == normalized(ref.get('topic', ''), self.config)
                    and idea.transformation == ref.get('transformation')
                    and normalized(idea.audience_question, self.config) == normalized(ref.get('audience_question', ''), self.config)):
                structural = 1.0
            for ours in (idea.one_sentence_premise, idea.audience_question):
                a = normalized(ours, self.config)
                for theirs in ref.get('texts', []):
                    b = normalized(theirs, self.config)
                    if not a or not b:
                        continue
                    compare_a, compare_b = a, b
                    if ref.get('generated') and same_topic:
                        subject = normalized(idea.topic, self.config)
                        compare_a, compare_b = a.replace(subject, ''), b.replace(subject, '')
                    seq = SequenceMatcher(None, compare_a, compare_b).ratio()
                    x, y = content_ngrams(compare_a), content_ngrams(compare_b)
                    overlap = len(x & y) / min(len(x), len(y)) if x and y else 0.0
                    score = 100 * max(seq, overlap, structural)
                    if score > best['similarity']:
                        best = {'similarity': score, 'reference': ref['id'],
                                'reason': 'Structured premise match' if structural else 'Character/trigram phrasing match'}
        score = best['similarity']
        best['status'] = 'REJECT' if score >= self.config['similarity_reject'] else 'REVIEW' if score >= self.config['similarity_review'] else 'CLEAR'
        best['limitation'] = 'Deterministic baseline; CLEAR does not certify originality.'
        return best


def references_for(briefs, candidates):
    lookup = {c['video_id']: c for c in candidates}
    return [{'id': b.video_id, 'topic': b.canonical_subject or '', 'transformation': b.competitor_angle,
             'audience_question': b.mechanism_question or '',
             'texts': [lookup[b.video_id]['title'], b.competitor_angle, b.context_summary or '']}
            for b in briefs]


def consolidate(ideas):
    """Merge exact structured duplicates, preserving superseded records and source lineage."""
    seen = {}
    for idea in sorted(ideas, key=lambda x: x.idea_id):
        key = (idea.cluster_id, idea.transformation, idea.audience_question.casefold())
        if key not in seen:
            seen[key] = idea
            continue
        kept = seen[key]
        idea.duplicate_of = kept.idea_id
        idea.similarity_status = 'REJECT'
        idea.risk_flags.append('REJECT_NEAR_DUPLICATE')
        for field in ('source_video_ids', 'story_brief_ids', 'material_claim_ids', 'evidence_ids', 'required_research', 'risk_flags'):
            # Do not transfer the duplicate's rejection flag to the canonical idea.
            values = getattr(idea, field)
            if field == 'risk_flags':
                values = [v for v in values if v != 'REJECT_NEAR_DUPLICATE']
            setattr(kept, field, sorted(set(getattr(kept, field) + values)))
    return ideas
