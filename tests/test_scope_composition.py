import copy
import json
from pathlib import Path
import unittest
from tech_uncovered.scripting.pivot_scope import classify,validate_candidate

class CompositionTests(unittest.TestCase):
    def setUp(self):
        data=json.loads((Path(__file__).parent/'fixtures/scope/composition.json').read_text())
        self.packet=data['packet'];self.candidate=data['candidate']
        self.props=self.candidate['raw_generated_content']['propositions']
    def test_exact_candidate(self):
        r=validate_candidate(self.candidate['raw_generated_content'],self.packet,'angle_refinement',self.candidate['candidate_id'])
        self.assertEqual((r['result'],r['next_status']),('PASS','CONTINUE'))
    def test_children_derive_mappings(self):
        r=classify(self.props[1],self.packet)
        for u in r['atomic_units']:
            self.assertTrue(u['claim_ids'] and u['passage_ids'] and u['evidence_ids'])
            self.assertLessEqual(set(u['claim_ids']),set(self.props[1]['claim_ids']))
        self.assertEqual(r['atomic_units'][0]['claim_ids'],['claim-6508cc49e0d34119'])
        self.assertEqual(r['atomic_units'][2]['claim_ids'],['claim-api-capabilities'])
    def test_unrelated_claim_cannot_support_child(self):
        p=copy.deepcopy(self.props[1]);p['claim_ids']=p['claim_ids'][:1];p['passage_ids']=p['passage_ids'][:1]
        self.assertNotEqual(classify(p,self.packet)['classification'],'SUPPORTED_COMPOSITE_PARAPHRASE')
    def test_uncited_passage_cannot_support_child(self):
        p=copy.deepcopy(self.props[2]);p['passage_ids']=['passage-beac863116ee521a']
        self.assertEqual(classify(p,self.packet)['classification'],'BROADER_THAN_EVIDENCE')
    def test_unknown_tool_rejected(self):
        p=copy.deepcopy(self.props[2]);p['text']=p['text'].replace('web search','mind reading')
        self.assertEqual(classify(p,self.packet)['classification'],'BROADER_THAN_EVIDENCE')
    def test_wrong_reasoning_count_rejected(self):
        p=copy.deepcopy(self.props[3]);p['text']=p['text'].replace('five','six')
        self.assertEqual(classify(p,self.packet)['classification'],'BROADER_THAN_EVIDENCE')
    def test_cautionary_reliability(self):
        for text in (self.props[5]['text'],'does not establish reliability','not proof of reliability','cannot be treated as reliable'):
            with self.subTest(text=text):
                self.assertEqual(classify({'text':text},self.packet)['classification'],'NONFACTUAL_EDITORIAL')
    def test_positive_reliability(self):
        for text in ('the tool is reliable','this proves reliability','not proof of reliability, but the tool is reliable'):
            with self.subTest(text=text):
                self.assertEqual(classify({'text':text},self.packet)['classification'],'FORBIDDEN_CATEGORY')
    def test_editorial_guidance(self):
        for i in (0,4,6):
            self.assertEqual(classify(self.props[i],self.packet)['classification'],'NONFACTUAL_EDITORIAL')
    def test_editorial_does_not_hide_assertion(self):
        p=copy.deepcopy(self.props[4]);p['text']+=' The model supports mind reading.'
        self.assertNotEqual(classify(p,self.packet)['classification'],'NONFACTUAL_EDITORIAL')
