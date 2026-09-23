import copy
import tempfile
import unittest
from pathlib import Path
from tech_uncovered.database import Database
from tech_uncovered.scripting.hooks import score_hooks
from tech_uncovered.scripting.fact_check import validate_check
from tech_uncovered.scripting.quality import spoken_diagnostics,review_quality
from tech_uncovered.scripting.readiness import decide
from tech_uncovered.scripting.providers.fixtures import FixtureScriptFactChecker
from tests.script_helpers import execute,fixture,config


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'test.db');self.b=fixture();self.r=execute(self.db,self.b)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def check(self,draft):
        raw=FixtureScriptFactChecker(self.b).check(draft,self.r['packet'],self.r['angle'],self.b['as_of'])
        return validate_check(raw,draft,self.r['packet'],self.b['as_of'])
    def test_supported_fixture_passes(self):self.assertEqual(self.r['check']['verdict'],'PASS')
    def test_angle_reframed_and_original_preserved(self):
        self.assertEqual(self.r['angle']['refinement_status'],'REFRAMED_FROM_ORIGINAL');self.assertIn('original_proposed_angle',self.r['angle'])
    def test_hook_weighted_score(self):
        hooks=copy.deepcopy(self.r['draft']['hook_candidates']);self.assertEqual(score_hooks(hooks,self.r['packet'])['hook_id'],'h1');self.assertAlmostEqual(hooks[0]['score'],92.7)
    def test_unsupported_hook_not_selected(self):
        hooks=copy.deepcopy(self.r['draft']['hook_candidates']);hooks[0]['claim_ids']=['bogus'];self.assertNotEqual(score_hooks(hooks,self.r['packet'])['hook_id'],'h1')
    def test_all_five_hooks_required(self):
        with self.assertRaises(ValueError):score_hooks(self.r['draft']['hook_candidates'][:4],self.r['packet'])
    def test_modified_fact_fails_semantic_check(self):
        draft=copy.deepcopy(self.r['draft']);draft['sections'][1]['sentences'][0]['text']='Nacre searches every PDF on the internet.'
        self.assertEqual(self.check(draft)['verdict'],'FAIL')
    def test_numbers_not_found_in_evidence_fail(self):
        draft=copy.deepcopy(self.r['draft']);draft['sections'][1]['sentences'][0]['text']='Search runs 999 times faster.'
        result=self.check(draft);self.assertTrue(any('UNSUPPORTED_NUMBER' in e for e in result['deterministic_issues']))
    def test_removed_mapping_fails(self):
        draft=copy.deepcopy(self.r['draft']);draft['sections'][1]['sentences'][0]['evidence_passage_ids']=[]
        self.assertEqual(self.check(draft)['verdict'],'FAIL')
    def test_title_checked(self):
        draft=copy.deepcopy(self.r['draft']);draft['title_working']='The fastest search ever';self.assertEqual(self.check(draft)['verdict'],'FAIL')
    def test_opinion_label_cannot_hide_false_fact(self):
        draft=copy.deepcopy(self.r['draft']);s=draft['sections'][1]['sentences'][0];s.update(statement_type='OPINION',materiality='SUPPORTING',text='It uploads all your files.')
        self.assertEqual(self.check(draft)['verdict'],'FAIL')
    def test_missing_checker_sentence_blocks(self):
        raw=FixtureScriptFactChecker(self.b).check(self.r['draft'],self.r['packet'],self.r['angle'],self.b['as_of']);raw['sentence_checks'].pop()
        self.assertEqual(validate_check(raw,self.r['draft'],self.r['packet'],self.b['as_of'])['verdict'],'FAIL')
    def test_quality_weighting(self):self.assertAlmostEqual(self.r['quality']['score'],91.45)
    def test_spoken_flags(self):
        draft=copy.deepcopy(self.r['draft']);draft['sections'][1]['sentences'][0]['text']='Furthermore, this incredible revolutionary game-changer means you should smash that subscribe button. '
        flags=spoken_diagnostics(draft)
        self.assertIn('UNNATURAL_TRANSITIONS',flags);self.assertIn('UNNECESSARY_SUPERLATIVES',flags);self.assertIn('ROBOTIC_CTA',flags)
    def test_duration_and_word_count(self):
        self.assertTrue(110<=self.r['draft']['word_count']<=150);self.assertTrue(45<=self.r['draft']['estimated_duration']<=60)
    def test_readiness_does_not_follow_score_alone(self):
        self.r['check']['verdict']='FAIL';self.assertEqual(self.decide()['status'],'RESEARCH_REQUIRED')
    def decide(self):return decide(self.r['packet'],self.r['draft'],self.r['check'],self.r['quality'],self.r['angle'],config())
    def test_minor_edits_need_explicit_acceptance(self):
        self.r['check']['verdict']='PASS_WITH_MINOR_EDITS';self.assertEqual(self.decide()['status'],'EDITORIAL_REVIEW')
    def test_originality_review_blocks_readiness(self):
        self.r['angle']['originality_status']='REVIEW';self.assertEqual(self.decide()['status'],'EDITORIAL_REVIEW')
    def test_originality_reject(self):
        self.r['quality']['originality_status']='REJECT';self.assertEqual(self.decide()['status'],'REJECTED')
    def test_spoken_warning_blocks_readiness(self):
        self.r['quality']['spoken_naturalness']['flags']=['ROBOTIC_CTA'];self.assertEqual(self.decide()['status'],'EDITORIAL_REVIEW')
    def test_long_script_blocks_readiness(self):
        self.r['draft']['word_count']=151;self.assertEqual(self.decide()['status'],'EDITORIAL_REVIEW')
    def test_factual_visual_note_fails(self):
        draft=copy.deepcopy(self.r['draft']);draft['visual_notes']=['Show caption: this search is 999 times faster.']
        self.assertEqual(self.check(draft)['verdict'],'FAIL')
    def test_on_screen_claim_requires_evidence(self):
        draft=copy.deepcopy(self.r['draft']);draft['on_screen_text']=[{'sentence_id':'screen-1','text':'It uploads no files.','statement_type':'FACT','claim_ids':[],'source_ids':[],'evidence_passage_ids':[]}]
        self.assertEqual(self.check(draft)['verdict'],'FAIL')
