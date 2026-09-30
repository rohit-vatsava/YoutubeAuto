import copy
import unittest
from unittest.mock import patch
from tech_uncovered.database import Database
from tech_uncovered.scripting.fact_check import validate_check
from tech_uncovered.scripting.pivot_scope import classify
from tests.m3_golden import setup,execute,NOW

class OnscreenSupportTests(unittest.TestCase):
    def setUp(self):
        p=patch('socket.socket.connect',side_effect=AssertionError('Offline only'));p.start();self.addCleanup(p.stop)
        db=Database(':memory:');self.addCleanup(db.close)
        bundle,cfg,choice=setup(db);result=execute(db,bundle,cfg,choice)
        self.draft=copy.deepcopy(result['draft']);self.packet=result['packet']
        self.raw=copy.deepcopy(result['check'])
        item=copy.deepcopy(self.draft['sections'][1]['sentences'][0]);item['sentence_id']='display-test'
        self.draft['on_screen_text']=[item];self.item=item
    def replay(self):return validate_check(copy.deepcopy(self.raw),self.draft,self.packet,NOW)
    def test_mapped_display_without_model_row_passes(self):
        self.assertEqual(self.replay()['verdict'],'PASS')
    def test_bullets_inherit_parent_mappings(self):
        self.item['text']='The AtlasDB 3 API supports three consistency settings: eventual • session • strong'
        decision=classify(dict(text=self.item['text'],factual=True,claim_ids=self.item['claim_ids'],evidence_ids=self.item['source_ids'],passage_ids=self.item['evidence_passage_ids']),self.packet)
        self.assertEqual(decision['classification'],'SUPPORTED_COMPOSITE_PARAPHRASE')
        for atom in decision['atomic_units']:
            self.assertEqual(atom['inherited_claim_ids'],self.item['claim_ids'])
            self.assertEqual(atom['evidence_ids'],self.item['source_ids'])
            self.assertEqual(atom['passage_ids'],self.item['evidence_passage_ids'])
        self.assertEqual(self.replay()['verdict'],'PASS')
    def test_caution_passes(self):
        self.item['text']='Listed support ≠ guaranteed availability, appropriateness, reliability, or workflow payoff.'
        self.assertEqual(self.replay()['verdict'],'PASS')
    def test_missing_mappings_fails(self):
        self.item.update(claim_ids=[],source_ids=[],evidence_passage_ids=[])
        self.assertIn('display-test:SEMANTIC_SUPPORT_MISSING',self.replay()['deterministic_issues'])
    def test_wrong_mappings_fail(self):
        for key in ('claim_ids','source_ids','evidence_passage_ids'):
            with self.subTest(key=key):
                old=self.item[key];self.item[key]=['wrong-id']
                self.assertEqual(self.replay()['verdict'],'FAIL');self.item[key]=old
    def test_unsupported_quoted_display_fails(self):
        self.item['text']="Display 'AtlasDB 3 is completely reliable.'"
        self.assertEqual(self.replay()['verdict'],'FAIL')
    def test_explicit_model_rejection_not_overridden(self):
        self.raw['sentence_checks'].append(dict(sentence_id='display-test',supported=False,issues=[],claim_ids=self.item['claim_ids'],source_ids=self.item['source_ids']))
        self.assertIn('display-test:SEMANTIC_SUPPORT_MISSING',self.replay()['deterministic_issues'])
    def test_missing_body_check_still_fails(self):
        self.raw['sentence_checks']=[c for c in self.raw['sentence_checks'] if c['sentence_id']!='s2']
        self.assertIn('s2:SEMANTIC_SUPPORT_MISSING',self.replay()['deterministic_issues'])
    def test_choreography_unchanged(self):
        self.draft['visual_notes']=['Use a two-card layout. Keep the two existing on-screen text elements visually separate.']
        self.assertEqual(self.replay()['verdict'],'PASS')
