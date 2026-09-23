import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock
from tech_uncovered.scripting.hook_scope import validate_hooks,apply_report
from tech_uncovered.scripting.hooks import score_hooks
from tech_uncovered.scripting.pivot_scope import classify
from tech_uncovered.scripting.scope_language import polarity
from tech_uncovered.scripting.pivot_scope import FORBIDDEN

class HookScopeTests(unittest.TestCase):
    def setUp(self):
        data=json.loads((Path(__file__).parent/'fixtures/scope/hooks.json').read_text())
        self.packet=data['packet'];self.raw=data['candidate']['raw_generated_content']
        self.hooks=self.raw['hook_candidates']
    def report(self):return validate_hooks(self.hooks,self.packet,'fixture')
    def test_exact_hooks(self):
        self.assertEqual(self.report()['eligible_hook_ids'],['hook-2','hook-5'])
    def test_inheritance(self):
        r=self.report()['propositions'][1]
        self.assertEqual(r['atomic_units'][0]['claim_ids'],['claim-api-capabilities'])
        self.assertTrue(r['atomic_units'][0]['passage_ids'])
        self.assertEqual(r['classification'],'SUPPORTED_COMPOSITE_PARAPHRASE')
    def test_not_guarantee(self):
        p=polarity("OpenAI’s documentation gives a list, not a workflow guarantee.",FORBIDDEN)
        self.assertEqual(p[0]['polarity'],'CAUTIONARY_NEGATION')
    def test_does_not_prove(self):
        self.assertEqual(classify({'text':'does not prove reliability'},self.packet)['classification'],'NONFACTUAL_EDITORIAL')
    def test_positive_reliability(self):
        self.assertEqual(classify({'text':'The tool is reliable'},self.packet)['classification'],'FORBIDDEN_CATEGORY')
    def test_one_bad_four_good(self):
        good=copy.deepcopy(self.hooks[1])
        self.hooks[:]=[dict(copy.deepcopy(good),hook_id=str(i)) for i in range(5)]
        self.hooks[0]['text']='The tool is reliable.'
        r=self.report();self.assertEqual(r['result'],'PASS');self.assertEqual(len(r['eligible_hook_ids']),4)
    def test_zero_survivors_blocks(self):
        for h in self.hooks:h['text']='The tool is reliable.'
        r=self.report();self.assertEqual(r['result'],'FAIL')
        apply_report(self.hooks,r)
        with self.assertRaisesRegex(ValueError,'No evidence-safe hook'):score_hooks(self.hooks,self.packet)
    def test_best_survivor(self):
        apply_report(self.hooks,self.report())
        selected=score_hooks(self.hooks,self.packet)
        self.assertEqual(selected['hook_id'],'hook-5')
        self.assertFalse(self.hooks[3]['eligible'])
    def test_unrelated_passages_fail(self):
        self.hooks[1]['evidence_passage_ids']=['passage-cb0d63f9c9fe4d3b']
        self.assertNotIn('hook-2',self.report()['eligible_hook_ids'])
    def test_positive_clause_not_hidden(self):
        self.hooks[1]['text']+=' The tool is reliable.'
        self.assertNotIn('hook-2',self.report()['eligible_hook_ids'])
    def test_resume_reuses_generation_without_calls(self):
        from tests.test_script_resume import ResumeTests
        from tech_uncovered.scripting.pipeline import run_accepted_pivot
        from tech_uncovered.scripting.costs import Budget
        f=ResumeTests();f.setUp();self.addCleanup(f.doCleanups)
        loaded=f.load();loaded['outline']={'beats':[]};loaded['outline_validation']={'result':'PASS'}
        loaded['generation']=copy.deepcopy(self.raw)
        generator=Mock();generator.name='fixture';generator.version='1';generator.scope_contract_version=2
        reviewer=Mock();reviewer.name='fixture';reviewer.version='1'
        result=run_accepted_pivot(f.f.db,{'selected':loaded['selected']},f.f.cfg,generator,reviewer,reviewer,Budget(f.f.cfg,offline=True),f.f.now,'synthetic',resume=loaded)
        generator.refine.assert_not_called();generator.outline.assert_not_called();generator.generate.assert_not_called()
        reviewer.check.assert_not_called()
        self.assertIn('script_generation',result['resume_metadata']['stages_reused'])
