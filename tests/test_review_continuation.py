import copy,json
import unittest
from unittest.mock import Mock,patch
from tests import test_editorial_revision as editorial_tests
from tests.m3_golden import NOW
from tech_uncovered.scripting.editorial_revision import create,load
from tech_uncovered.scripting.review_continuation import prepare,continue_quality
from tech_uncovered.scripting.providers.fixtures import FixtureScriptFactChecker,FixtureQualityReviewer
from tech_uncovered.scripting.fact_check import validate_check
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting import storage

class ReviewContinuationTests(unittest.TestCase):
    def setUp(self):
        editorial_tests.EditorialRevisionTests.setUp(self)
        self.manifest,self.path=create(self.reports,self.sid,self.edits,self.db,NOW,self.cfg)
        self.draft=json.loads((self.path/'script.json').read_text())
        self.packet=json.loads((self.folder/'research_packet.json').read_text())
        self.bundle['approved_sentence_texts']+=list(self.edits.values())
        self.check=validate_check(FixtureScriptFactChecker(self.bundle).check(self.draft,self.packet,{},NOW),self.draft,self.packet,NOW)
        self.save_check(self.check)
    def save_check(self,check):
        (self.path/'fact_check.json').write_text(json.dumps(check))
        self.db.connection.execute('DELETE FROM script_fact_checks WHERE script_run_id=? AND revision=2',(self.sid,))
        if check:storage.save_review(self.db,'script_fact_checks',check)
    def prepared(self):return prepare(self.reports,self.sid,2,self.db,NOW,self.cfg)
    def test_pass_quality_only_and_history_preserved(self):
        loaded=self.prepared();self.assertTrue(loaded['eligible_to_continue'])
        before=(self.path/'fact_check.json').read_bytes();events=[];budget=Budget(self.cfg,offline=True)
        reviewer=Mock()
        def quality(*args):
            events.append('quality');budget.record.model_calls+=1
            return FixtureQualityReviewer(self.bundle).review(*args)
        reviewer.review.side_effect=quality
        from tech_uncovered.scripting.readiness import decide
        def readiness(*args):events.append('readiness');return decide(*args)
        with patch('tech_uncovered.scripting.review_continuation.decide',side_effect=readiness),patch('tech_uncovered.scripting.providers.fixtures.FixtureScriptFactChecker.check',side_effect=AssertionError('No fact check')),patch('tech_uncovered.scripting.pipeline.collect',side_effect=AssertionError('No research')),patch('tech_uncovered.scripting.providers.fixtures.FixtureScriptGenerator.generate',side_effect=AssertionError('No generation')):
            result=continue_quality(loaded,self.db,reviewer,budget,NOW,self.cfg)
        self.assertEqual(events,['quality','readiness']);self.assertEqual(reviewer.review.call_count,1)
        self.assertEqual(result['readiness']['status'],'READY_FOR_PRODUCTION')
        self.assertEqual(result['costs']['quality_review_cost']['model_calls'],1)
        self.assertEqual(result['costs']['fact_check_cost'].get('model_calls',0),0)
        self.assertEqual(result['costs']['search_calls'],0)
        self.assertEqual(before,(self.path/'fact_check.json').read_bytes())
        self.assertTrue(json.loads((self.path/'quality-continuation/provenance.json').read_text())['no_new_model_call'])
        with self.assertRaises(ValueError):self.prepared()
    def test_missing_check_blocks(self):
        self.save_check(None)
        with self.assertRaisesRegex(ValueError,'Missing'):self.prepared()
    def test_nonpassing_model_verdict_blocks(self):
        for verdict in ('FAIL','RESEARCH_REQUIRED','PASS_WITH_MINOR_EDITS'):
            with self.subTest(verdict=verdict):
                check=copy.deepcopy(self.check);check['model_verdict']=verdict;self.save_check(check)
                with self.assertRaises(ValueError):self.prepared()
    def test_blocking_findings_and_deterministic_failure_block(self):
        for mutate in (lambda r:r.update(unsupported_sentences=[dict(text='bad',severity='ERROR',blocking=True)]),lambda r:r.update(title_supported=False)):
            check=copy.deepcopy(self.check);mutate(check);self.save_check(check)
            with self.assertRaises(ValueError):self.prepared()
    def test_existing_quality_blocks(self):
        (self.path/'quality_review.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'already exists'):self.prepared()
    def test_provenance_mismatch_blocks(self):
        draft=copy.deepcopy(self.draft);draft['full_script']='changed';(self.path/'script.json').write_text(json.dumps(draft))
        with self.assertRaises(ValueError):self.prepared()
    def test_final_readiness_blocks(self):
        (self.path/'readiness.json').write_text(json.dumps({'status':'READY_FOR_PRODUCTION'}))
        with self.assertRaisesRegex(ValueError,'final'):self.prepared()
    def test_normal_resume_still_blocks(self):
        with self.assertRaisesRegex(ValueError,'already'):load(self.reports,self.sid,2,self.db,NOW,self.cfg)
    def test_low_quality_remains_editorial(self):
        reviewer=Mock();raw=copy.deepcopy(self.bundle['quality']);raw['components']={k:0 for k in raw['components']};reviewer.review.return_value=raw
        result=continue_quality(self.prepared(),self.db,reviewer,Budget(self.cfg,offline=True),NOW,self.cfg)
        self.assertEqual(result['readiness']['status'],'EDITORIAL_REVIEW')
    def test_cli_dry_run_never_constructs_model(self):
        import argparse
        from tech_uncovered.scripting.cli import add_parser,execute
        parser=argparse.ArgumentParser();add_parser(parser.add_subparsers())
        args=parser.parse_args(['script','--continue-review',self.sid,'--revision','2','--dry-run'])
        with patch('tech_uncovered.scripting.cli.Database',return_value=self.db),patch('tech_uncovered.scripting.cli.configuration',return_value=self.cfg),patch('tech_uncovered.scripting.review_continuation.prepare',return_value=self.prepared()),patch('tech_uncovered.scripting.providers.openai_live.OpenAIModel',side_effect=AssertionError('No model')),patch('builtins.print'):
            self.assertEqual(execute(args),0)
    def test_cli_safety_failure_precedes_provider(self):
        import argparse
        from tech_uncovered.scripting.cli import add_parser,execute
        parser=argparse.ArgumentParser();add_parser(parser.add_subparsers())
        args=parser.parse_args(['script','--continue-review',self.sid,'--revision','2'])
        with patch('tech_uncovered.scripting.cli.Database',return_value=self.db),patch('tech_uncovered.scripting.cli.configuration',return_value=self.cfg),patch('tech_uncovered.scripting.review_continuation.prepare',side_effect=ValueError('Ineligible')),patch('tech_uncovered.scripting.providers.openai_live.OpenAIModel',side_effect=AssertionError('No model')),patch('builtins.print'):
            self.assertNotEqual(execute(args),0)
