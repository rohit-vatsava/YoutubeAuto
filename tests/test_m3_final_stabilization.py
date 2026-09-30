import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch

from tech_uncovered.database import Database
from tech_uncovered.scripting.fact_check import normalize_findings,validate_check,FINDING_FIELDS
from tech_uncovered.scripting.scope_language import caution_clause,polarity
from tech_uncovered.scripting.pivot_scope import classify,FORBIDDEN
from tech_uncovered.scripting.readiness import decide
from tech_uncovered.scripting.storage import boundary
from tech_uncovered.scripting.providers.fixtures import FixtureScriptFactChecker
from tech_uncovered.scripting.providers.openai_live import ModelScriptFactChecker,ModelScriptGenerator
from tech_uncovered.scripting.models import json_schema
from tests.script_helpers import execute,fixture,config


class FinalStabilizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.db=Database(Path(cls.tmp.name)/'fixture.sqlite3')
        cls.bundle=fixture()
        with patch('socket.socket.connect',side_effect=AssertionError('No network')),patch('socket.create_connection',side_effect=AssertionError('No network')):
            cls.result=execute(cls.db,cls.bundle)
    @classmethod
    def tearDownClass(cls):
        cls.db.close();cls.tmp.cleanup()
    def setUp(self):
        self.r=copy.deepcopy(self.result)
        self.raw=FixtureScriptFactChecker(self.bundle).check(self.r['draft'],self.r['packet'],self.r['angle'],self.bundle['as_of'])
    def check(self):
        return validate_check(self.raw,self.r['draft'],self.r['packet'],self.bundle['as_of'])
    def readiness(self):
        return decide(self.r['packet'],self.r['draft'],self.r['check'],self.r['quality'],self.r['angle'],config())
    def test_caution_punctuation_and_quotes(self):
        for text in ('"Not a guarantee."','(does not prove reliability)','No evidence shows reliability.',
                     'cannot conclude reliability','not necessarily available','does not establish reliability',
                     '; “does not prove.”','not a guarantee','does not prove','cannot conclude','no evidence shows',
                     'listed support is not a guarantee of reliability','does not prove a specific workflow payoff'):
            with self.subTest(text=text):
                self.assertTrue(caution_clause(text))
                self.assertFalse(any(p['polarity']=='ASSERTION' for p in polarity(text,FORBIDDEN)))
                self.assertEqual(classify({'text':text},self.r['packet'])['classification'],'NONFACTUAL_EDITORIAL')
    def test_multisentence_cautions(self):
        text='Not a guarantee. Does not prove reliability.'
        self.assertEqual(classify({'text':text},self.r['packet'])['classification'],'NONFACTUAL_EDITORIAL')
    def test_quoted_visual_caution_scopes_only_its_own_occurrence(self):
        text='Show “Not a guarantee.” The tool is reliable.'
        values=polarity(text,FORBIDDEN)
        self.assertEqual([x['polarity'] for x in values],['CAUTIONARY_NEGATION','ASSERTION'])
        self.assertEqual(polarity('Open on a card reading “Documentation ≠ workflow guarantee.”',FORBIDDEN)[0]['polarity'],'CAUTIONARY_NEGATION')
    def test_positive_reliability_blocks(self):
        for text in ('The tool is reliable','The tool guarantees reliability','This proves reliability','It always works'):
            with self.subTest(text=text):
                self.assertEqual(classify({'text':text},self.r['packet'])['classification'],'FORBIDDEN_CATEGORY')
    def test_quote_cannot_exempt_positive_claim(self):
        for text in ('The tool is reliable, despite the label "not a guarantee".',
                     '"Not a guarantee." It always works.','Not a guarantee, but it is reliable.'):
            self.assertEqual(classify({'text':text},self.r['packet'])['classification'],'FORBIDDEN_CATEGORY')
    def test_typed_info_does_not_block(self):
        self.raw['timeline_issues']=[dict(category='TIMELINE',severity='INFO',blocking=False,text='No unsupported launch timing claim appears.')]
        r=self.check();self.assertEqual(r['verdict'],'PASS');self.assertEqual(r['blocking_issues'],[])
        self.assertEqual(r['observations'][0]['severity'],'INFO')
    def test_typed_error_blocks(self):
        self.raw['unsupported_sentences']=[dict(category='UNSUPPORTED_CLAIM',severity='ERROR',blocking=True,text='Unsupported assertion.')]
        r=self.check();self.assertEqual(r['verdict'],'FAIL')
        self.assertIsInstance(r['deterministic_issues'][-1],dict)
        self.assertTrue(r['blocking_issues'][0]['blocking'])
    def test_legacy_reassurance_stays_blocking(self):
        self.raw['timeline_issues']=['No launch claim appears; script correctly avoids timing claims.']
        r=self.check();self.assertEqual(r['verdict'],'FAIL');self.assertTrue(r['blocking_issues'][0]['legacy_untyped'])
    def test_corrections_are_typed_and_blocking(self):
        self.raw['corrections']=['Change unsupported wording']
        self.assertEqual(self.check()['verdict'],'FAIL')
    def test_sentence_info_does_not_block(self):
        self.raw['sentence_checks'][0]['issues']=[dict(category='ATTRIBUTION',severity='INFO',blocking=False,text='Attribution retained.')]
        self.assertEqual(self.check()['verdict'],'PASS')
    def test_warning_defaults_nonblocking(self):
        row=normalize_findings([dict(category='EDIT',severity='WARNING',text='Minor edit.')],'TEST')[0]
        self.assertFalse(row['blocking'])
    def test_explicit_blocking_honored(self):
        for severity,blocking in [('INFO',True),('ERROR',False),('UNKNOWN',False)]:
            row=normalize_findings([dict(severity=severity,blocking=blocking,text='Opaque text',extra={'id':1})],'TEST')[0]
            self.assertEqual(row['blocking'],blocking);self.assertEqual(row['extra'],{'id':1})
    def test_invalid_types_fail_closed(self):
        for row in ({'severity':'UNKNOWN','text':'Unknown'}, {'severity':'INFO','blocking':'false','text':'Unknown'}, {'severity':'INFO'}):
            self.assertTrue(normalize_findings([row],'TEST')[0]['blocking'])
    def test_deterministic_checks_still_block(self):
        self.raw['title_supported']=False
        self.raw['timeline_issues']=[dict(category='TIMELINE',severity='INFO',blocking=False,text='All good here')]
        r=self.check();self.assertEqual(r['verdict'],'FAIL');self.assertIn('UNSUPPORTED_TITLE',r['deterministic_issues'])
    def test_normalization_idempotent(self):
        self.raw['timeline_issues']=[dict(category='TIMELINE',severity='INFO',blocking=False,text='Observation')]
        first=copy.deepcopy(self.check());second=self.check()
        self.assertEqual(first,second)
    def test_word_count_boundaries(self):
        for count,status in [(139,'READY_FOR_PRODUCTION'),(150,'READY_FOR_PRODUCTION'),(151,'EDITORIAL_REVIEW')]:
            self.r['draft'].update(word_count=count,estimated_duration=count/150*60)
            self.assertEqual(self.readiness()['status'],status)
        self.assertIn('WORD_COUNT_OUTSIDE_BOUNDS',self.readiness()['reasons'])
    def test_readiness_pure_verdict_truth_table(self):
        for verdict,status in [('PASS','READY_FOR_PRODUCTION'),('PASS_WITH_MINOR_EDITS','EDITORIAL_REVIEW'),
                               ('RESEARCH_REQUIRED','RESEARCH_REQUIRED'),('FAIL','RESEARCH_REQUIRED')]:
            self.r['check']['verdict']=verdict
            before=copy.deepcopy(self.r)
            self.assertEqual(self.readiness()['status'],status);self.assertEqual(self.r,before)
    def test_quality_threshold(self):
        self.r['quality']['score']=config()['quality_threshold']-1
        self.assertEqual(self.readiness()['status'],'EDITORIAL_REVIEW')
    def test_observations_do_not_downgrade(self):
        self.r['check']['observations']=[dict(category='ANY',severity='INFO',blocking=False,text='Arbitrary opaque observation')]
        self.assertEqual(self.readiness()['status'],'READY_FOR_PRODUCTION')
    def test_none_db_preserves_bookkeeping(self):
        result={'resume_metadata':{'stages_executed':[]}}
        boundary(None,result,'fact_check');boundary(None,result,'fact_check')
        self.assertEqual(result['completed_stages'],['fact_check'])
        self.assertEqual(result['resume_metadata']['boundaries_executed'],['fact_check'])
        self.assertEqual(result['resume_snapshot']['completed_stages'],['fact_check'])
    def test_model_contract_typed_without_call(self):
        model=Mock();model.config=config()
        ModelScriptFactChecker(model).check(self.r['draft'],self.r['packet'],self.r['angle'],self.bundle['as_of'])
        args=model.request.call_args.args;schema=json_schema(args[3])
        for field in FINDING_FIELDS:
            item=schema['properties'][field]['items']
            self.assertEqual(item['type'],'object');self.assertEqual(set(item['required']),{'category','severity','blocking','text'})
        self.assertIn('Only actual factual defects',args[1])
    def test_generation_targets_headroom(self):
        model=Mock();model.config=config()
        ModelScriptGenerator(model).generate(self.r['packet'],self.r['angle'],self.r['outline'])
        instructions=model.request.call_args.args[1]
        self.assertIn('Target 130–140 words',instructions);self.assertIn('Do not exceed 150 words',instructions)
        self.assertEqual(config()['script_word_min'],110);self.assertEqual(config()['script_word_max'],150)
    def test_offline_golden_path(self):
        self.assertEqual(self.r['readiness']['status'],'READY_FOR_PRODUCTION')
        self.assertEqual(self.r['check']['verdict'],'PASS')
        for name in ('model_calls','search_calls','fetch_attempts','actual_cost_usd'):
            self.assertEqual(self.r['cost'][name],0)
        self.assertGreaterEqual(self.r['quality']['score'],config()['quality_threshold'])
