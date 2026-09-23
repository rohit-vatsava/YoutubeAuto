import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock,patch
from tech_uncovered.scripting.resume import load_resume,promote
from tech_uncovered.scripting.pipeline import run_accepted_pivot
from tech_uncovered.scripting.reports import export
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.models import digest


class ResumeTests(unittest.TestCase):
    def setUp(self):
        from tests.test_pivot_acceptance import PivotAcceptanceTests
        self.f=PivotAcceptanceTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        result=self.f.run_pivot()
        # Simulate an older validator rejecting a persisted editorial candidate.
        raw=dict(scope_contract_version=2,angle='There is a catch.',payoff='Here is what the docs actually say.',
            evidence_basis=['c3'],originality_status='REVIEW',editorial_status='READY',propositions=[
                dict(text='There is a catch.',factual=False,surface='angle'),
                dict(text='Here is what the docs actually say.',factual=False,surface='payoff')])
        candidate=dict(candidate_id='saved-candidate',stage='angle_refinement',raw_generated_content=raw,validation_result='FAIL')
        result.update(angle=None,outline=None,draft=None,generation_candidates=[candidate],revisions=[])
        payload=json.loads(self.f.db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(result['script_id'],)).fetchone()[0])
        payload.update(angle=None,outline=None,generation_candidates=[candidate])
        with self.f.db.connection:
            self.f.db.connection.execute('UPDATE script_runs SET payload=? WHERE script_run_id=?',(json.dumps(payload),result['script_id']))
        self.root=self.f.root/'reports';self.folder=export(result,self.root);self.result=result
    def load(self):return load_resume(self.root,self.result['script_id'],self.f.db,self.f.now,self.f.cfg)
    def test_load_validates_exact_candidate_offline(self):
        loaded=self.load();self.assertEqual(loaded['candidate']['raw_generated_content'],self.result['generation_candidates'][0]['raw_generated_content'])
        self.assertEqual(loaded['validation']['result'],'PASS');self.assertEqual(loaded['validation']['next_status'],'CONTINUE')
    def test_promotion_preserves_every_original_audit(self):
        before={p.name:p.read_bytes() for p in self.folder.iterdir() if p.name!='angle.json'}
        loaded=self.load();promote(loaded)
        self.assertEqual(json.loads((self.folder/'angle.json').read_text()),loaded['angle'])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.folder.iterdir() if p.name!='angle.json'})
        self.load()  # idempotent promotion is compatible
    def test_resume_first_stage_outline_never_refine_or_research(self):
        loaded=self.load();budget=Budget(self.f.cfg,offline=True)
        generator=Mock();generator.name='fixture';generator.version='1';generator.scope_contract_version=2
        generator.refine.side_effect=AssertionError('Angle refinement must be skipped')
        def outline(packet,angle):
            self.assertEqual(angle['angle'],loaded['angle']['angle'])
            budget.record.model_calls+=1
            raise RuntimeError('Stop fixture at first new stage')
        generator.outline.side_effect=outline
        reviewer=Mock();reviewer.name='fixture';reviewer.version='1'
        before=copy.deepcopy(loaded)
        resumed=run_accepted_pivot(self.f.db,{'selected':loaded['selected']},self.f.cfg,generator,reviewer,reviewer,budget,self.f.now,'synthetic',resume=loaded)
        generator.refine.assert_not_called();generator.outline.assert_called_once();generator.generate.assert_not_called()
        self.assertEqual(resumed['resume_metadata']['stages_executed'],['script_outline'])
        self.assertEqual(resumed['resume_metadata']['resumed_from_script_id'],self.result['script_id'])
        self.assertEqual(resumed['packet']['source_research_run_id'],loaded['packet']['source_research_run_id'])
        self.assertEqual(resumed['pivot_acceptance'],loaded['packet']['pivot_acceptance'])
        self.assertEqual(resumed['selected'],loaded['selected']);self.assertEqual(loaded,before)
        self.assertEqual(resumed['cost']['model_calls'],1);self.assertEqual(resumed['cost']['search_calls'],0)
        self.assertEqual(resumed['cost']['fetch_attempts'],0);self.assertEqual(resumed['cost']['story_resolution_cost']['model_calls'],0)
        self.assertNotEqual(resumed['script_id'],self.result['script_id'])
        folder=export(resumed,self.root)
        self.assertTrue((folder/'resume_metadata.json').exists())
        saved=json.loads(self.f.db.connection.execute('SELECT payload FROM script_runs WHERE script_run_id=?',(resumed['script_id'],)).fetchone()[0])
        self.assertEqual(saved['resume_metadata'],resumed['resume_metadata'])
    def test_changed_candidate_rejected_before_model(self):
        p=self.folder/'angle_candidate.json';data=json.loads(p.read_text());data['raw_generated_content']['angle']='Tampered';p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'database audit'):self.load()
    def test_current_validator_failure_stops_before_promotion(self):
        before=(self.folder/'angle.json').read_bytes()
        with patch('tech_uncovered.scripting.resume.validate_candidate',return_value={'result':'FAIL','next_status':'EDITORIAL_REVIEW','rejected_spans':[{'text':'unsafe'}]}):
            with self.assertRaisesRegex(ValueError,'scope rejected'):self.load()
        self.assertEqual((self.folder/'angle.json').read_bytes(),before)
    def test_cli_rejects_failed_resume_without_constructing_model(self):
        from tech_uncovered.cli import main
        with patch('tech_uncovered.scripting.resume.load_resume',side_effect=ValueError('scope rejected')),patch('tech_uncovered.scripting.providers.openai_live.OpenAIModel') as model:
            code=main(['script','--resume',self.result['script_id'],'--db',str(self.f.path if hasattr(self.f,'path') else self.f.root/'test.db'),'--reports-dir',str(self.root)])
        self.assertEqual(code,1);model.assert_not_called()
    def test_stale_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError,'stale'):load_resume(self.root,self.result['script_id'],self.f.db,'2030-01-01T00:00:00+00:00',self.f.cfg)
    def test_unsafe_script_path_rejected(self):
        with self.assertRaises(ValueError):load_resume(self.root,'../../secret',self.f.db,self.f.now,self.f.cfg)
