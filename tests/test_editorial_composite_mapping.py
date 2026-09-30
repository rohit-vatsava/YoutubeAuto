import copy,unittest
from tests import test_onscreen_support as fixtures
from tech_uncovered.scripting.pivot_scope import classify,FAILURES
from tech_uncovered.scripting.hooks import mapping_errors
from tech_uncovered.scripting.fact_check import validate_check
from tests.m3_golden import NOW

class EditorialCompositeMappingTests(unittest.TestCase):
    def setUp(self):
        fixtures.OnscreenSupportTests.setUp(self)
        self.packet['pivot_acceptance']={'allowed_claim_scope':{c['claim_id']:{} for c in self.packet['claims']}}
        self.row=dict(sentence_id='editorial',text='Pick the settings you need. Test them in your environment. Consider measuring task success.',factual=False,statement_type='editorial guidance',materiality='material',claim_ids=[],source_ids=[],evidence_passage_ids=[])
    def classify(self,row):
        return classify(dict(text=row['text'],factual=row['factual'],claim_ids=row['claim_ids'],evidence_ids=row['source_ids'],passage_ids=row['evidence_passage_ids']),self.packet)
    def test_all_children_and_parent_editorial(self):
        result=self.classify(self.row)
        self.assertEqual(result['classification'],'NONFACTUAL_EDITORIAL')
        self.assertEqual([c['classification'] for c in result['atomic_units']],['NONFACTUAL_EDITORIAL']*3)
        self.assertEqual(mapping_errors(self.row,self.packet),[])
    def test_move_position_irrelevant(self):
        for name in ('Payoff','Setup'):
            draft=copy.deepcopy(self.draft);draft['sections'].append({'name':name,'sentences':[self.row]})
            raw=copy.deepcopy(self.raw);raw['sentence_checks'].append(dict(sentence_id='editorial',supported=True,material=False,claim_ids=[],source_ids=[],issues=[]))
            self.assertEqual(validate_check(raw,draft,self.packet,NOW)['verdict'],'PASS')
    def test_factual_child_still_rejected(self):
        for text in ('Test them because the model is reliable.','Pick the settings you need. The model supports teleportation.'):
            row=dict(self.row,text=text)
            self.assertIn(self.classify(row)['classification'],FAILURES)
            self.assertIn('MISSING_CLAIM_MAPPING',mapping_errors(row,self.packet))
    def test_factual_setup_missing_mapping_is_single_diagnostic(self):
        draft=copy.deepcopy(self.draft);row=dict(self.row,text='The model supports teleportation.',factual=True)
        draft['sections'].append({'name':'Setup','sentences':[row]})
        raw=copy.deepcopy(self.raw);raw['sentence_checks'].append(dict(sentence_id='editorial',supported=True,material=True,claim_ids=[],source_ids=[],issues=[]))
        result=validate_check(raw,draft,self.packet,NOW)
        self.assertEqual(result['verdict'],'FAIL')
        self.assertEqual([x for x in result['deterministic_issues'] if isinstance(x,str) and 'MISSING_CLAIM_MAPPING' in x],['editorial:MISSING_CLAIM_MAPPING'])
    def test_correct_factual_mapping_unchanged(self):
        self.assertEqual(mapping_errors(self.item,self.packet),[])
        self.assertNotIn(self.classify(self.item)['classification'],FAILURES)
