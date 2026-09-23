import unittest
from copy import deepcopy
from tech_uncovered.intelligence.models import StoryBrief
from tech_uncovered.intelligence.generation import DeterministicIdeaGenerator
from tech_uncovered.intelligence.similarity import DeterministicSimilarityChecker,consolidate
from tests.intelligence_helpers import config


class SimilarityTests(unittest.TestCase):
    def setUp(self):
        b=StoryBrief(video_id='a',canonical_subject='Orbit compiler')
        self.idea=DeterministicIdeaGenerator().generate(b,{'cluster_id':'t'})[0]
        self.checker=DeterministicSimilarityChecker(config())

    def test_copy_premise_rejected(self):
        result=self.checker.check(self.idea,[{'id':'source','texts':[self.idea.one_sentence_premise]}])
        self.assertEqual(result['status'],'REJECT')
        self.assertEqual(result['similarity'],100)

    def test_competitor_summary_also_checked(self):
        refs=[{'id':'summary','texts':['Unrelated title',self.idea.audience_question]}]
        self.assertEqual(self.checker.check(self.idea,refs)['status'],'REJECT')

    def test_structured_question_equivalence(self):
        refs=[{'id':'x','topic':self.idea.topic,'transformation':self.idea.transformation,
               'audience_question':self.idea.audience_question,'texts':['Different surface wording']}]
        self.assertEqual(self.checker.check(self.idea,refs)['status'],'REJECT')

    def test_alias_normalization(self):
        self.idea.topic='artificial intelligence';self.idea.audience_question='How does artificial intelligence work?'
        refs=[{'id':'x','topic':'ai','transformation':self.idea.transformation,'audience_question':'How does ai work?', 'texts':['Different']}]
        self.assertEqual(self.checker.check(self.idea,refs)['status'],'REJECT')

    def test_distinct_topic_same_template_not_plagiarism(self):
        other=deepcopy(self.idea);other.topic='Pebble AI model'
        other.one_sentence_premise=other.one_sentence_premise.replace('Orbit compiler',other.topic)
        other.audience_question=other.audience_question.replace('Orbit compiler',other.topic)
        refs=[{'id':'other','generated':True,'topic':other.topic,'texts':[other.one_sentence_premise,other.audience_question]}]
        self.assertEqual(self.checker.check(self.idea,refs)['status'],'CLEAR')

    def test_consolidation_preserves_sources(self):
        other=deepcopy(self.idea);other.idea_id='zz';other.source_video_ids=['b']
        rows=consolidate([other,self.idea])
        rejected=[i for i in rows if i.duplicate_of]
        self.assertEqual(len(rejected),1)
        self.assertEqual(set(self.idea.source_video_ids),{'a','b'})
        self.assertNotIn('REJECT_NEAR_DUPLICATE',self.idea.risk_flags)
