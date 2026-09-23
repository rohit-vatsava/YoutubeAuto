import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tech_uncovered.scripting.pivot_scope import classify,compact_bundle,validate_candidate
from tech_uncovered.scripting.pivot_acceptance import accept
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.pivots import recommend_pivot
from tech_uncovered.scripting.providers.openai_live import pivot_angle_request,build_payload,OpenAIModel,ModelScriptGenerator
from tech_uncovered.scripting.costs import Budget
from tests.test_evidence_linking import inputs
from tests.script_helpers import config


def scoped_packet():
    raw,sources,plan,selected,outcome=inputs()
    packet=validate_packet(raw,sources,plan,selected)
    packet['research_run_id']='source-run'
    recommend_pivot(packet,plan,selected,outcome)
    _,scoped=accept(dict(packet=packet,pivot=packet['angle_pivot'],plan=plan,sources=sources,
        selected=selected,artifact_path='fixture',artifact_hash='fixture'),plan['planned_at'])
    return scoped


def proposition(packet,text,cid='1',factual=True):
    claim=next(c for c in packet['claims'] if c['claim_id']==cid)
    return dict(text=text,factual=factual,claim_ids=[cid],evidence_ids=claim['evidence_ids'],passage_ids=[p['passage_id'] for p in claim['passages']])


class ScopeTests(unittest.TestCase):
    def setUp(self):
        self.p=scoped_packet()
        for target in ('socket.create_connection','socket.getaddrinfo'):
            guard=patch(target,side_effect=AssertionError('No network'));guard.start();self.addCleanup(guard.stop)
    def classify(self,text,cid='1'):return classify(proposition(self.p,text,cid),self.p)['classification']
    def test_supported_api_paraphrase(self):
        self.assertEqual(self.classify('Nacre documents computer use as supported for One through the Responses API.'),'SUPPORTED_PARAPHRASE')
    def test_supported_passive_paraphrase(self):
        self.assertEqual(self.classify('Computer use is listed as supported in the Responses API.'),'SUPPORTED_PARAPHRASE')
    def test_numeric_equivalence(self):
        self.assertEqual(self.classify('The model page lists a 0.024 million-token context window.','3'),'SUPPORTED_PARAPHRASE')
    def test_fine_tuning_paraphrase(self):
        self.assertEqual(self.classify('Nacre lists fine-tuning as unsupported.','2'),'SUPPORTED_PARAPHRASE')
    def test_context_wrong_number(self):
        self.assertEqual(self.classify('The model page lists a 25,000-token context window.','3'),'BROADER_THAN_EVIDENCE')
    def test_api_omission_blocked(self):self.assertEqual(self.classify('Computer use is supported.'),'BROADER_THAN_EVIDENCE')
    def test_api_other_endpoint_blocked(self):self.assertEqual(self.classify('Nacre documents computer use as supported in the Realtime API.'),'BROADER_THAN_EVIDENCE')
    def test_extra_assertion_not_entailed(self):self.assertEqual(self.classify('Computer use is listed as supported in the Responses API and runs without supervision.'),'BROADER_THAN_EVIDENCE')
    def test_customization_broadening(self):self.assertEqual(self.classify('Nacre One can never be customized.','2'),'BROADER_THAN_EVIDENCE')
    def test_reliability_blocked(self):self.assertEqual(self.classify('One can reliably control any computer.'),'FORBIDDEN_CATEGORY')
    def test_superiority_blocked(self):self.assertEqual(self.classify('One is the best computer-use model.'),'FORBIDDEN_CATEGORY')
    def test_all_forbidden_categories(self):
        for sentence in ('It launched yesterday.','Breaking news today.','This is AGI.','It beats everyone.','A benchmark proves it.','Better than competing models.','It is reliable.','It is safe to deploy.'):
            self.assertEqual(self.classify(sentence),'FORBIDDEN_CATEGORY',sentence)
    def test_nonfactual_editorial(self):
        p=dict(text='There is a catch.',factual=False,claim_ids=[])
        self.assertEqual(classify(p,self.p)['classification'],'NONFACTUAL_EDITORIAL')
    def test_nonfactual_hook_mapping(self):
        from tech_uncovered.scripting.hooks import mapping_errors
        self.assertEqual(mapping_errors(dict(text='Here is what the docs actually say.',factual=False,claim_ids=[],source_ids=[],evidence_passage_ids=[]),self.p),[])
    def test_factual_cannot_hide_as_editorial(self):
        self.assertEqual(classify(dict(text='The model reads minds.',factual=False,claim_ids=[]),self.p)['classification'],'NEW_UNSUPPORTED_CLAIM')
    def test_explicit_claim_required(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');p['claim_ids']=[]
        self.assertEqual(classify(p,self.p)['classification'],'NEW_UNSUPPORTED_CLAIM')
    def test_unknown_claim(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');p['claim_ids']=['invented']
        self.assertEqual(classify(p,self.p)['classification'],'NEW_UNSUPPORTED_CLAIM')
    def test_wrong_passage(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');p['passage_ids']=['bogus']
        self.assertEqual(classify(p,self.p)['classification'],'NEW_UNSUPPORTED_CLAIM')
    def test_wrong_source(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');p['evidence_ids']=['bogus']
        self.assertEqual(classify(p,self.p)['classification'],'NEW_UNSUPPORTED_CLAIM')
    def test_mapped_but_unverified_rejected(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');self.p['claims'][1]['status']='UNVERIFIED'
        self.assertEqual(classify(p,self.p)['classification'],'NEW_UNSUPPORTED_CLAIM')
    def test_lack_of_api_passage_rejected(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');p['passage_ids']=p['passage_ids'][1:]
        self.assertEqual(classify(p,self.p)['classification'],'BROADER_THAN_EVIDENCE')
    def test_exact_wording(self):self.assertEqual(self.classify(self.p['claims'][1]['supported_wording']),'SUPPORTED_EXACT')
    def test_editorial_failure_not_research(self):
        p=proposition(self.p,'Nacre One can never be customized.','2')
        r=validate_candidate({'propositions':[p]},self.p,'script_outline','candidate-fixture')
        self.assertEqual(r['next_status'],'EDITORIAL_REVIEW');self.assertEqual(r['rejected_spans'][0]['text'],p['text'])
    def test_new_thesis_needs_research(self):
        p=proposition(self.p,'The model reads minds.');p['claim_ids']=['new-thesis']
        r=validate_candidate({'propositions':[p]},self.p,'script_outline','candidate-fixture')
        self.assertEqual(r['next_status'],'RESEARCH_REQUIRED')
    def test_surface_cannot_hide_new_fact(self):
        p=proposition(self.p,'Computer use is listed as supported in the Responses API.');p['surface']='angle'
        r=validate_candidate({'angle':p['text']+' It reads minds.','payoff':'There is a catch.','propositions':[p]},self.p,'angle_refinement','c')
        self.assertEqual(r['result'],'FAIL')
    def test_compaction_complete_no_history(self):
        self.p['radar_payload']='SHOULD_NOT_APPEAR';self.p['source_records'][0]['text']+=' HISTORY_CANARY'
        bundle=compact_bundle(self.p,config());text=json.dumps(bundle)
        self.assertNotIn('HISTORY_CANARY',text);self.assertNotIn('SHOULD_NOT_APPEAR',text);self.assertNotIn('source_records',text)
        self.assertEqual(len(bundle['claims']),5);self.assertEqual(len(bundle['passages']),7)
        self.assertEqual(set(bundle['allowed_claim_ids']),{c['claim_id'] for c in bundle['claims']})
    def test_request_metrics_recorded_without_transport(self):
        cfg=config();budget=Budget(cfg,offline=True);budget.finish_research()
        response={'usage':{'input_tokens':1,'output_tokens':1},'output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]}
        model=OpenAIModel('fixture',cfg,budget,transport=lambda payload:response)
        ModelScriptGenerator(model).refine(self.p,{})
        attempt=budget.record.attempts[0]
        self.assertGreater(attempt['evidence_bundle_tokens'],0);self.assertEqual(attempt['historical_context_tokens'],0)
        self.assertLess(attempt['payload_bytes'],30000)


class AuditTests(unittest.TestCase):
    def setUp(self):
        from tests.test_pivot_acceptance import PivotAcceptanceTests
        self.fixture=PivotAcceptanceTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.f=self.fixture
    def candidate(self,text='There is a catch.'):
        return dict(self.f.bundle['angle'],scope_contract_version=2,angle=text,payoff='Here is what the docs actually say.',
            propositions=[dict(text=text,factual=False,claim_ids=[],evidence_ids=[],passage_ids=[],surface='angle'),
                dict(text='Here is what the docs actually say.',factual=False,claim_ids=[],evidence_ids=[],passage_ids=[],surface='payoff')],
            editorial_status='READY')
    def test_raw_committed_before_validator_even_if_validator_crashes(self):
        self.f.bundle['angle']=self.candidate()
        def fail_after_check(raw,packet,stage,candidate_id):
            row=self.f.db.connection.execute('SELECT payload FROM script_runs ORDER BY rowid DESC').fetchone()
            saved=json.loads(row[0])['generation_candidates'][-1]
            self.assertEqual(saved['validation_result'],'PENDING');self.assertEqual(saved['raw_generated_content'],self.f.bundle['angle'])
            raise RuntimeError('Deliberate fixture validator crash')
        with patch('tech_uncovered.scripting.generation_audit.validate_candidate',side_effect=fail_after_check):result=self.f.run_pivot()
        self.assertTrue(result['generation_candidates']);self.assertTrue(result['failures'])
    def test_exact_rejected_span_and_editorial_status_persisted(self):
        angle=self.candidate('This model can never be customized.')
        angle['propositions'][0].update(factual=True,claim_ids=['c4'],evidence_ids=['src-nacre'],passage_ids=['passage-ed5e69374a13a9c1'])
        self.f.bundle['angle']=angle;result=self.f.run_pivot()
        self.assertEqual(result['readiness']['status'],'EDITORIAL_REVIEW')
        from tech_uncovered.scripting.reports import export
        folder=export(result,self.f.root/'reports')
        candidate=json.loads((folder/'angle_candidate.json').read_text());report=json.loads((folder/'scope_validation.json').read_text())
        self.assertEqual(candidate['raw_generated_content'],angle)
        self.assertEqual(report['rejected_spans'][0]['text'],'This model can never be customized.')
        self.assertIn('This model can never be customized.',result['failures'][0]['reason'])
    def test_editorial_return_without_new_fact_is_editorial_review(self):
        self.f.bundle['angle']=self.candidate();self.f.bundle['angle']['editorial_status']='EDITORIAL_REVIEW'
        result=self.f.run_pivot();self.assertEqual(result['readiness']['status'],'EDITORIAL_REVIEW')
    def test_legacy_failed_generation_still_retains_raw_script_and_hooks(self):
        self.f.bundle['draft']['hook_candidates']=[]
        result=self.f.run_pivot()
        stages={c['stage'] for c in result['generation_candidates']}
        self.assertTrue({'angle_refinement','script_outline','hooks','script_generation'}<=stages)
        self.assertTrue(result['failures'])
