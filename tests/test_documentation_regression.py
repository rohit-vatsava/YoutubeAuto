import copy
import unittest
from unittest.mock import patch
from test_evidence_linking import inputs
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.pivots import recommend_pivot
from tech_uncovered.scripting.pivot_acceptance import accept, SKIPPED, STAGES

class DocumentationRegressionTests(unittest.TestCase):
    def setUp(self):
        self.raw,self.sources,self.plan,self.selected,self.outcome=inputs()
        self.raw['claims']=self.raw['claims'][:2]
        self.raw['claims'][0]['claim_type']='IDENTITY_AVAILABILITY'
        self.raw['claims'][1]['claim_type']='TECHNICAL_DOCUMENTATION'
        self.sources[0]['text']+=' Use it for coding and research. reasoning.effort supports low , high . Tools supported by this model when using the Responses API. Computer use Supported MCP Supported Snapshots'
        self.plan['comparison_required']=False
        self.plan['requirement_queue']=[dict(requirement_id='workflow',category='TECHNICAL_MECHANISM')]
        self.outcome.update(requirements_attempted=['workflow'],angle_unsupported_reason='RESEARCH_ATTEMPTED_WITHOUT_SUFFICIENT_SUPPORT')
        self.raw['safe_angle']='Nacre’s documentation lists Nacre One as an API model with configurable reasoning effort and Responses-API tool support; what remains unproven is any specific workflow payoff.'
    def packet(self):
        with patch('socket.socket.connect',side_effect=AssertionError('No network')):
            return validate_packet(self.raw,copy.deepcopy(self.sources),self.plan,self.selected)
    def test_new_claim_types_reach_extraction(self):
        self.assertTrue(all(c['passages'] and c['passage_ids'] for c in self.packet()['claims']))
    def test_rationale_without_links_diagnosed(self):
        self.raw['claims'][1].update(claim_type='UNKNOWN',rationale='The page explicitly supports this.')
        self.assertEqual(self.packet()['evidence_link_diagnostics'][0]['code'],'SUPPORT_RATIONALE_WITHOUT_LINKED_EVIDENCE')
    def test_angle_failure_keeps_evidence(self):
        p=self.packet();recommend_pivot(p,self.plan,self.selected,self.outcome)
        self.assertEqual(p['research_evidence_status'],'PARTIAL')
        self.assertEqual(p['angle_feasibility_status'],'ANGLE_UNSUPPORTED')
    def test_docs_independent_of_freshness(self):
        p=self.packet();self.assertFalse(p['freshness']['established'])
        self.assertEqual(p['claims'][1]['status'],'VERIFIED')
    def test_workflow_never_repaired(self):
        self.raw['claims'][1]['claim_type']='WORKFLOW_IMPLICATION'
        self.assertEqual(self.packet()['claims'][1]['status'],'UNVERIFIED')
    def test_safe_pivot_requires_linked_evidence(self):
        p=self.packet();self.assertIsNotNone(recommend_pivot(p,self.plan,self.selected,self.outcome))
        p['claims'][1]['passages']=[]
        self.assertIsNone(recommend_pivot(p,self.plan,self.selected,self.outcome))
    def test_arbitrary_safe_angle_rejected(self):
        p=self.packet();p['safe_angle']='The model improves productivity'
        self.assertIsNone(recommend_pivot(p,self.plan,self.selected,self.outcome))
    def test_saved_pivot_preserves_research_and_skips(self):
        p=self.packet();pivot=recommend_pivot(p,self.plan,self.selected,self.outcome)
        p['research_run_id']='original-research'
        candidate=dict(packet=p,pivot=pivot,plan=self.plan,sources=self.sources,artifact_path='/saved',artifact_hash='hash')
        acceptance,scoped=accept(candidate,self.plan['planned_at'])
        self.assertEqual(scoped['source_research_run_id'],'original-research')
        self.assertIn('research_synthesis',SKIPPED)
        self.assertEqual(STAGES[0],'angle_refinement')
        self.assertIn('PRODUCTIVITY_IMPROVEMENT',acceptance['forbidden_claims'])
    def test_unfetched_source_does_not_link(self):
        self.sources[0]['acquisition_state']='DISCOVERED'
        self.assertEqual(self.packet()['research_status'],'INSUFFICIENT')
