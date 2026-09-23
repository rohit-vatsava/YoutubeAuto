import copy
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from tech_uncovered.database import Database
from tech_uncovered.scripting.planning import BoundedResearchPlanner
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.sources import priority,independent_sources,public_url
from tech_uncovered.scripting.costs import Budget,LimitReached,ProviderFailure
from tech_uncovered.scripting.research import collect
from tech_uncovered.scripting.providers.fixtures import FixtureResearchProvider,FixtureResearchSynthesizer
from tests.script_helpers import fixture,config,selected


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=Database(Path(self.tmp.name)/'test.db');self.choice=selected(self.db)
        self.b=fixture();self.cfg=config();self.plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.b['as_of'])
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def packet(self,b=None):
        b=b or self.b
        return validate_packet(b['packet'],b['sources'],self.plan,self.choice)
    def test_plan_maps_questions_and_resets_inherited_verification(self):
        self.choice['idea']['story_context']=[{'entities':['Nacre'],'factual_claims':[{'claim_id':'old','text':'Claim','status':'VERIFIED'}]}]
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.b['as_of'])
        self.assertEqual(plan['claims_to_verify'][0]['status'],'UNVERIFIED');self.assertEqual(len(plan['key_questions']),4)
        self.assertTrue(all(q['question_id'] and q['query'] for q in plan['key_questions']))
    def test_source_priority_formula(self):
        self.assertEqual(priority({'authority_score':80,'relevance_score':60,'freshness_score':40}),66)
    def test_primary_low_rank_can_establish_claim(self):
        self.b['sources'][0]['authority_score']=1;self.b['sources'][0]['source_priority']=1
        self.assertEqual(self.packet()['research_status'],'SUFFICIENT')
    def test_high_rank_is_not_verification(self):
        self.b['packet']['source_assessments']=[];self.b['sources'][0]['source_priority']=100
        self.assertEqual(self.packet()['research_status'],'INSUFFICIENT')
    def test_exact_quotes_required(self):
        self.b['packet']['claims'][0]['passages'][0]['quote']='Invented quote about a product that is absent.'
        self.assertNotEqual(self.packet()['research_status'],'SUFFICIENT')
    def test_contradiction_blocks_script(self):self.assertEqual(self.packet(fixture('contradictory_research.json'))['research_status'],'CONTRADICTED')
    def test_no_core_claims_insufficient(self):
        self.b['packet']['core_claim_ids']=[];self.assertNotEqual(self.packet()['research_status'],'SUFFICIENT')
    def test_freshness_is_required(self):
        self.b['sources'][0]['publication_date']=None;self.assertFalse(self.packet()['freshness']['established'])
    def test_future_event_is_not_fresh(self):
        self.b['packet']['freshness']['event_date']='2027-01-01T00:00:00+00:00';self.assertNotEqual(self.packet()['research_status'],'SUFFICIENT')
    def test_remaining_material_questions_block(self):
        self.b['packet']['remaining_questions_material']=True;self.assertNotEqual(self.packet()['research_status'],'SUFFICIENT')
    def test_requirements_need_evidence(self):
        self.b['packet']['requirement_resolutions'][0]['claim_ids']=['nonexistent'];self.assertTrue(self.packet()['unresolved_requirements'])
    def test_partial_claim_requires_qualification(self):
        self.b['packet']['claims'][0]['status']='PARTIALLY_VERIFIED';self.assertNotEqual(self.packet()['research_status'],'SUFFICIENT')
    def test_syndicated_sources_are_one(self):
        a=self.b['sources'][0];b=copy.deepcopy(a);b['source_id']='copy';b['url']='https://copy.example/story';b['content_hash']='different'
        self.assertEqual(len(independent_sources([a,b])),1)
    def test_early_stop_after_one_source_and_search(self):
        p,s,out=collect(FixtureResearchProvider(self.b),FixtureResearchSynthesizer(self.b),self.plan,self.choice,Budget(self.cfg,offline=True))
        self.assertEqual(out['logical_search_calls'],1);self.assertEqual(len(s),1);self.assertEqual(out['stop_reason'],'EVIDENCE_SUFFICIENT')
    def test_source_failure_isolated(self):
        provider=FixtureResearchProvider(self.b);search=provider.search
        provider.search=lambda *a,**k:[{'url':'https://bad.example','authority_score':100,'relevance_score':100,'freshness_score':100}]+search(*a,**k)
        p,s,out=collect(provider,FixtureResearchSynthesizer(self.b),self.plan,self.choice,Budget(self.cfg,offline=True))
        self.assertEqual(p['research_status'],'SUFFICIENT');self.assertEqual(len(out['failures']),1)
    def test_time_limit_stops(self):
        clock=[0];budget=Budget(self.cfg,offline=True,clock=lambda:clock[0]);clock[0]=301
        p,s,out=collect(FixtureResearchProvider(self.b),FixtureResearchSynthesizer(self.b),self.plan,self.choice,budget)
        self.assertIsNone(p);self.assertIn('time limit',out['stop_reason'])
    def test_private_destinations_blocked(self):
        for url in ('file:///etc/passwd','http://example.com','https://user:pass@example.com','https://example.com:8443'):
            with self.assertRaises(ProviderFailure):public_url(url)
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(ProviderFailure):public_url('https://example.com')
