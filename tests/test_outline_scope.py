import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch,Mock
from tech_uncovered.scripting import pivot_scope
from tech_uncovered.scripting.pipeline import run_accepted_pivot
from tech_uncovered.scripting.costs import Budget

class OutlineScopeTests(unittest.TestCase):
    def setUp(self):
        self.data=json.loads((Path(__file__).parent/'fixtures/scope/outline.json').read_text())
        self.raw=self.data['candidate']['raw_generated_content'];self.packet=self.data['packet']
    def validate(self):
        return pivot_scope.validate_candidate(self.raw,self.packet,'script_outline','fixture')
    def test_exact_outline(self):
        r=self.validate();self.assertEqual((r['result'],r['next_status']),('PASS','CONTINUE'))
    def test_same_classifier(self):
        with patch.object(pivot_scope,'classify',wraps=pivot_scope.classify) as c:
            self.validate()
            self.assertEqual(c.call_count,len(self.raw['propositions']))
    def test_atomic_mappings(self):
        for p in self.validate()['propositions']:
            for a in p.get('atomic_units',[]):
                self.assertTrue(a['inherited_claim_ids'] and a['evidence_ids'] and a['passage_ids'])
    def test_negative_reliability(self):
        self.assertEqual(self.validate()['propositions'][5]['classification'],'NONFACTUAL_EDITORIAL')
    def test_editorial_planning(self):
        for i in (1,6,7):self.assertEqual(self.validate()['propositions'][i]['classification'],'NONFACTUAL_EDITORIAL')
    def test_mixed_coverage_preserves_words(self):
        self.assertEqual(self.validate()['result'],'PASS')
        self.raw['beats'][0]['purpose']+=' It is reliable.'
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_unsupported_tool(self):
        for p in self.raw['propositions']:p['text']=p['text'].replace('web search','mind reading')
        self.assertEqual(self.validate()['result'],'FAIL')
    def test_positive_reliability(self):
        self.raw['propositions'][5]['text']='The tool is reliable.'
        self.assertEqual(self.validate()['propositions'][5]['classification'],'FORBIDDEN_CATEGORY')
    def test_resume_skips_outline(self):
        from tests.test_script_resume import ResumeTests
        f=ResumeTests();f.setUp();self.addCleanup(f.doCleanups)
        loaded=f.load()
        loaded['outline']=copy.deepcopy(self.raw)
        loaded['outline_validation']=self.validate()
        generator=Mock();generator.name='fixture';generator.version='1';generator.scope_contract_version=2
        generator.refine.side_effect=AssertionError('must skip angle')
        generator.outline.side_effect=AssertionError('must skip outline')
        generator.generate.side_effect=RuntimeError('Stop at first newly executed stage')
        reviewer=Mock();reviewer.name='fixture';reviewer.version='1'
        result=run_accepted_pivot(f.f.db,{'selected':loaded['selected']},f.f.cfg,generator,reviewer,reviewer,Budget(f.f.cfg,offline=True),f.f.now,'synthetic',resume=loaded)
        generator.refine.assert_not_called();generator.outline.assert_not_called();generator.generate.assert_called_once()
        self.assertEqual(result['resume_metadata']['stages_executed'],['script_generation'])
        self.assertIn('script_outline',result['resume_metadata']['stages_reused'])
        self.assertEqual(generator.generate.call_args.args[2],loaded['outline'])
