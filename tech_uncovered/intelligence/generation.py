from .models import IdeaCandidate, stable_id

# Original templates, inspired by the reference's editorial discipline, not copied hooks.
DIRECTIONS = (
    ('mechanism', 'What happens inside {topic}, step by step?', 'Investigate the mechanism behind {topic} using a simple input-to-output diagram.'),
    ('practical example', 'Which everyday task is a useful test of {topic}?', 'Evaluate {topic} on a small, reproducible task with explicit success criteria.'),
    ('comparison', 'What trade-off should someone weigh before using {topic}?', 'Compare one decision-relevant trade-off around {topic}, including when an alternative may fit better.'),
    ('implications', 'What would need to change in a workflow to use {topic}?', 'Examine the workflow implications of {topic}, separating documented capabilities from assumptions.'),
    ('history', 'Which earlier approach helps explain {topic}?', 'Place {topic} in context by comparing its design goal with an earlier approach.'),
)


EVERGREEN_DIRECTIONS = (
    ('explanation', 'How can {topic} be explained with a clear example?', 'Explain a basic concept in {topic} using an original diagram.'),
    ('practical lesson', 'What can a beginner practise to understand {topic}?', 'Develop a small practice exercise about {topic}; verify the lesson before presenting it.'),
    ('misconception', 'Which potential misunderstanding about {topic} is worth checking?', 'Investigate a possible misconception about {topic}; establish whether it is actually held before correcting it.'),
    ('mechanism', 'How does one process in {topic} work?', 'Explain one well-supported process in {topic}, step by step.'),
)


class DeterministicIdeaGenerator:
    name, version = 'adjacent-directions', '2.4'

    def generate(self, brief, cluster):
        from .opportunities import concrete
        if brief.story_context_status == 'INSUFFICIENT_CONTEXT' or not concrete(brief.canonical_subject):
            return []
        topic = brief.canonical_subject
        if (cluster.get('match_basis') or [None])[0] in {'radar_subject', 'metadata_evergreen'}:
            topic = cluster['canonical_topic']
        from .entry_contract import subject_type, apply
        kind_of_subject = subject_type({'canonical_subject':topic,'topic':topic,'named_entities':brief.named_entities or brief.entities,'story_context':[brief.to_dict()]})
        claims = brief.factual_claims + brief.uncertain_claims
        material = [c for c in claims if c.get('material', True)]
        research = [c['text'] for c in material if c['status'] != 'VERIFIED']
        # Factual grounding of a story does not verify a newly proposed example/comparison.
        directions = list(EVERGREEN_DIRECTIONS) if brief.story_type == 'EVERGREEN_TOPIC' else [d for d in DIRECTIONS if d[0] != brief.competitor_angle][:4]
        if brief.story_type == 'EVENT_STORY':
            # Do not invent a comparison target or a historical narrative.
            comparison_supported = brief.alleged_event == 'comparison'
            directions = [d for d in directions if d[0] != 'history' and (d[0] != 'comparison' or comparison_supported)]
        if kind_of_subject == 'PERSON':
            directions = [d for d in directions if d[0] != 'comparison']
        ideas = []
        for kind, question, premise in directions:
            extra = {
                'mechanism': 'Verify every step of the mechanism against primary documentation.',
                'practical example': 'Run and document an original reproducible example; do not reuse competitor examples.',
                'comparison': 'Choose and verify a relevant alternative and a like-for-like comparison criterion.',
                'implications': 'Validate the proposed workflow consequence with a concrete documented case.',
                'history': 'Verify the earlier approach and the historical comparison.',
                'explanation': 'Verify the underlying concept against reliable technical sources.',
                'practical lesson': 'Test an original practice exercise and document its limitations.',
                'misconception': 'Verify both the alleged misunderstanding and its correction; do not manufacture a myth.'}[kind]
            event = brief.alleged_event or brief.core_event or 'development'
            if kind_of_subject == 'COMPANY':
                replacements = {
                    'comparison': ('What evidence supports comparing {topic} with a named alternative on a specific business criterion?', 'Define and verify a like-for-like business comparison involving {topic}; do not infer a criterion or counterpart.'),
                    'mechanism': ('Which documented business process helps explain the reported {event} involving {topic}?', 'Investigate a documented business process relevant to {topic} and the reported {event}; distinguish evidence from assumptions.'),
                    'implications': ('Why does the reported {event} involving {topic} matter to developers or users?', 'Examine documented practical consequences of the reported {event} involving {topic}, without speculating about motives.'),
                    'practical example': ('What practical consequence of the reported {event} involving {topic} can be established?', 'Illustrate one evidence-supported consequence of the reported {event} involving {topic} with an original example.'),
                }
                question, premise = replacements.get(kind, (question,premise))
            elif kind_of_subject == 'PERSON':
                replacements = {
                    'mechanism': ('What documented technical or business idea did {topic} discuss in the reported {event}?', 'Explain a documented idea attributed to {topic}; verify the original statement and its context.'),
                    'implications': ('Why might the documented position attributed to {topic} matter?', 'Evaluate the implications of a documented statement by {topic}; distinguish their argument from established facts.'),
                    'practical example': ('Which original example could clarify a documented idea discussed by {topic}?', 'Build an original example to explain a verified statement by {topic}; do not infer private intentions.'),
                }
                question, premise = replacements.get(kind, (question,premise))
            elif kind_of_subject in {'EVENT','SECURITY_EVENT','BUSINESS_EVENT'}:
                replacements = {
                    'comparison': ('What evidence supports a comparison of the reported {event} involving {topic} with a named alternative?', 'Verify a specific comparison criterion and counterpart before comparing the reported {event} involving {topic}.'),
                    'mechanism': ('What documented mechanism explains the reported {event} involving {topic}?', 'Explain the documented mechanism of the reported {event} involving {topic}; verify each step.'),
                    'implications': ('What consequences of the reported {event} involving {topic} are supported?', 'Investigate documented consequences of the reported {event} involving {topic}.'),
                    'practical example': ('What original example could explain the reported {event} involving {topic}?', 'Illustrate the reported {event} involving {topic} with an independently checked example.'),
                }
                question, premise = replacements.get(kind, (question,premise))
            idea = IdeaCandidate(
                idea_id=stable_id('idea', [brief.video_id, kind]), source_video_ids=[brief.video_id],
                canonical_subject=topic, named_entities=list(brief.named_entities or brief.entities),
                alleged_event=brief.alleged_event or brief.core_event,
                topic=topic, proposed_angle=kind, audience_question=question.format(topic=topic,event=event),
                one_sentence_premise=premise.format(topic=topic,event=event),
                why_now=('Evergreen educational topic; no new event or current-timing claim.' if brief.story_type == 'EVERGREEN_TOPIC' else brief.why_now or 'Recent competitor coverage is an observation; current significance requires research.'),
                story_type=brief.story_type, story_context_status=brief.story_context_status, subject_type=kind_of_subject,
                originality_notes=f'Changes the explanation objective to {kind}; no competitor title or script is used as generated copy.',
                required_research=sorted(set(research + [extra])),
                potential_visuals=['Original labelled diagram', 'Self-created example with an annotated before/after'],
                risk_flags=list(brief.flags), confidence=brief.confidence,
                cluster_id=cluster['cluster_id'], story_brief_ids=[brief.video_id],
                material_claim_ids=sorted(c['claim_id'] for c in material),
                evidence_ids=sorted({e for c in material for e in c['evidence_ids']}),
                do_not_copy=['Competitor title, distinctive phrasing, metaphors, examples, or claim sequence'],
                transformation=kind,
                production_assumptions={'single_question': True, 'single_mechanism_or_example': True,
                                        'at_most_three_material_claims': len(material) <= 3,
                                        'achievable_diagrams_or_screens': True, 'no_bespoke_footage': True},
                expansion_sections=['mechanism', 'comparison', 'application', 'limitations/history'])
            apply(idea)
            ideas.append(idea)
        return ideas
