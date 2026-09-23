import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from tech_uncovered.database import Database
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.planning import BoundedResearchPlanner
from tech_uncovered.scripting.pivot_acceptance import accept, scope_issues, dry_run, load_candidate
from tech_uncovered.scripting.pipeline import run_accepted_pivot
from tech_uncovered.scripting.providers.fixtures import FixtureScriptGenerator,FixtureScriptFactChecker,FixtureQualityReviewer
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.reports import export
from tests.script_helpers import fixture,selected,config
from tests.test_evidence_linking import inputs
from tech_uncovered.scripting.pivots import recommend_pivot


class PivotAcceptanceTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection','socket.getaddrinfo','tech_uncovered.scripting.providers.openai_live.OpenAIModel.request',
                       'tech_uncovered.scripting.pipeline.collect','tech_uncovered.scripting.pipeline.StoryResolutionGate.resolve'):
            guard=patch(target,side_effect=AssertionError('No research or live calls'));guard.start();self.addCleanup(guard.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.db=Database(self.root/'test.db');self.addCleanup(self.db.close)
        self.choice=selected(self.db);self.bundle=fixture();self.cfg=config();self.now=self.bundle['as_of']
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.now)
        packet=validate_packet(self.bundle['packet'],self.bundle['sources'],plan,self.choice)
        packet.update(research_run_id='old-research',research_packet_id='old-packet',research_status='PARTIAL')
        for c in packet['claims']:c['verification_scope']='SUPPORTED_WORDING_ONLY'
        packet['claims'][0]['supported_wording']=packet['claims'][0]['supported_wording'].split('. ',1)[1]
        self.candidate=dict(packet=packet,pivot=dict(status='ANGLE_PIVOT_RECOMMENDED',original_angle='comparison',
            recommended_angle=self.bundle['angle']['angle'],verified_claim_ids_supporting_pivot=['c2','c3','c4'],pivot_requires_new_research=False),
            selected=self.choice,plan=plan,sources=self.bundle['sources'],artifact_path='fictional',artifact_hash='fixture')
    def run_pivot(self):
        return run_accepted_pivot(self.db,self.candidate,self.cfg,FixtureScriptGenerator(self.bundle),
            FixtureScriptFactChecker(self.bundle),FixtureQualityReviewer(self.bundle),Budget(self.cfg,offline=True),self.now,'synthetic')
    def test_evergreen_ready_skips_all_research_and_network(self):
        result=self.run_pivot();self.assertEqual(result['readiness']['status'],'READY_FOR_PRODUCTION')
        for key in ('search_calls','fetched_pages','fetch_attempts','model_calls'):self.assertEqual(result['cost'][key],0)
        self.assertEqual(result['packet']['freshness']['mode'],'EVERGREEN')
        self.assertEqual(result['packet']['freshness']['event_date'],'')
        self.assertEqual(result['research_outcome']['logical_search_calls'],0)
        self.assertEqual(result['packet']['original_angle_outcome'],'ANGLE_UNSUPPORTED')
    def test_accept_rejects_required_research(self):
        self.candidate['pivot']['pivot_requires_new_research']=True
        with self.assertRaises(ValueError):accept(self.candidate,self.now)
    def test_accept_requires_recommendation(self):
        self.candidate['pivot']['status']='UNSUPPORTED'
        with self.assertRaises(ValueError):accept(self.candidate,self.now)
    def test_new_claim_stops_before_check_and_review(self):
        self.bundle['draft']['sections'][0]['sentences'][0]['claim_ids']=['invented']
        result=self.run_pivot();self.assertEqual(result['readiness']['status'],'RESEARCH_REQUIRED')
        self.assertIsNone(result['check']);self.assertIsNone(result['quality'])
    def test_comparison_cannot_reenter(self):
        self.bundle['draft']['sections'][0]['sentences'][0]['text']='This model outperforms Rival.'
        self.assertEqual(self.run_pivot()['readiness']['status'],'RESEARCH_REQUIRED')
    def test_launch_cannot_reenter(self):
        self.bundle['draft']['sections'][0]['sentences'][0]['text']='It just launched today.'
        self.assertEqual(self.run_pivot()['readiness']['status'],'RESEARCH_REQUIRED')
    def test_each_traceability_mapping_required(self):
        _,packet=accept(self.candidate,self.now)
        for key in ('claim_ids','source_ids','evidence_passage_ids'):
            draft=copy.deepcopy(self.bundle['draft']);draft['sections'][0]['sentences'][0][key]=[]
            self.assertTrue(scope_issues(draft,packet,draft=True))
    def test_semantically_new_claim_with_valid_ids_fails(self):
        self.bundle['draft']['sections'][0]['sentences'][0]['text']='The software can understand every spoken language.'
        result=self.run_pivot();self.assertEqual(result['readiness']['status'],'RESEARCH_REQUIRED')
        self.assertEqual(result['check']['verdict'],'FAIL');self.assertIsNone(result['quality'])
    def test_acceptance_persisted_and_original_unchanged(self):
        before=copy.deepcopy(self.candidate);result=self.run_pivot();folder=export(result,self.root/'reports')
        acceptance=json.loads((folder/'pivot_acceptance.json').read_text())
        self.assertEqual(acceptance['editorial_status'],'ACCEPTED');self.assertEqual(acceptance['source_research_run_id'],'old-research')
        self.assertEqual(self.candidate,before)
        saved=json.loads(self.db.connection.execute('SELECT payload FROM research_packets').fetchone()[0])
        self.assertEqual(saved['pivot_acceptance'],acceptance)
        self.assertNotEqual(saved['research_run_id'],'old-research')
    def test_reject_originality(self):
        self.bundle['angle']['originality_status']='REJECT'
        self.assertEqual(self.run_pivot()['readiness']['status'],'REJECTED')
    def test_cli_dry_run_does_not_enter_historical_research_path(self):
        from tech_uncovered.cli import main
        with patch('tech_uncovered.scripting.pivot_acceptance.load_latest',return_value=self.candidate):
            code=main(['script','--idea-id',self.choice['idea']['idea_id'],'--accept-pivot','--offline','--dry-run','--reports-dir',str(self.root/'cli')])
        self.assertEqual(code,0);self.assertTrue((self.root/'cli/pivot_acceptance.json').exists())
    def test_dry_run_cost_bound_no_model(self):
        report=dry_run(self.candidate,self.cfg,self.now,self.root/'dry')
        self.assertEqual(report['projected_model_calls']['initial'],5)
        self.assertEqual(report['projected_model_calls']['with_one_editorial_revision'],8)
        self.assertEqual(report['projected_maximum_cost_usd'],1.)
        self.assertEqual(report['actual_cost_usd'],0)
    def test_out_of_scope_refinement_stops(self):
        self.bundle['angle']['evidence_basis']=['comparison-alternative']
        result=self.run_pivot();self.assertEqual(result['readiness']['status'],'RESEARCH_REQUIRED');self.assertIsNone(result['draft'])


class PivotLoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.original=self.root/'scripts/script-fixture';self.original.mkdir(parents=True);self.folder=self.root/'replay';self.folder.mkdir()
        raw,sources,plan,selected,outcome=inputs();selected.update(radar_run_id='radar',intelligence_run_id='intel')
        raw.update(idea_id='i',research_run_id='r',research_packet_id='p',radar_run_id='radar',intelligence_run_id='intel')
        self.now=plan['planned_at'];self.cfg=config()
        for name,obj in [('research_packet',raw),('research_plan',plan),('sources',sources),('idea',selected),('research_outcome',outcome)]:
            (self.original/(name+'.json')).write_text(json.dumps(obj))
        packet=validate_packet(raw,copy.deepcopy(sources),plan,selected);pivot=recommend_pivot(packet,plan,selected,outcome)
        (self.folder/'research_packet.json').write_text(json.dumps(packet));(self.folder/'angle_pivot.json').write_text(json.dumps(pivot))
    def load(self):return load_candidate(self.folder,'i',self.root/'scripts',self.now,self.cfg)
    def test_load_reproducible_candidate(self):self.assertEqual(self.load()['packet']['idea_id'],'i')
    def test_tampered_claim_rejected(self):
        path=self.folder/'research_packet.json';p=json.loads(path.read_text());p['claims'][1]['supported_wording']='Invented';path.write_text(json.dumps(p))
        with self.assertRaises(ValueError):self.load()
    def test_stale_evidence_rejected(self):
        self.now='2027-01-01T00:00:00+00:00'
        with self.assertRaises(ValueError):self.load()
    def test_new_research_pivot_rejected(self):
        for name in ('angle_pivot','research_packet'):
            path=self.folder/(name+'.json');p=json.loads(path.read_text());(p if name=='angle_pivot' else p['angle_pivot'])['pivot_requires_new_research']=True;path.write_text(json.dumps(p))
        with self.assertRaises(ValueError):self.load()
