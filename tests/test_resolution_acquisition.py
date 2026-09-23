import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from tech_uncovered.scripting.resolution import validate_resolution, StoryResolutionGate
from tech_uncovered.scripting.resolution_replay import replay
from tech_uncovered.scripting.providers.openai_live import OpenAIModel
from tech_uncovered.scripting.models import SourceRecord
from tech_uncovered.scripting.costs import Budget, ProviderFailure
from tech_uncovered.scripting.research import collect
from tech_uncovered.scripting.planning import BoundedResearchPlanner
from tech_uncovered.scripting.providers.fixtures import FixtureResearchSynthesizer
from tests.script_helpers import fixture, config


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection','socket.getaddrinfo','tech_uncovered.scripting.providers.openai_live.OpenAIModel.request'):
            p=patch(target,side_effect=AssertionError('Network/model calls forbidden'));p.start();self.addCleanup(p.stop)
        self.bundle=fixture();self.raw=copy.deepcopy(self.bundle['story_resolution'])
        self.source=self.bundle['sources'][0]
        self.choice={'competitor_references':[], 'idea':{'topic':'Nacre desktop search','source_video_ids':[],
                     'story_context':[],'risk_flags':[],'audience_question':'How does it work?','proposed_angle':'mechanism',
                     'required_research':[],'idea_id':'test'}}
        self.cfg=dict(config(),resolution_authorities={'nacre.example':'Nacre'})
        self.hits=[{'url':self.source['url'],'result_title':'Nacre desktop search preview release',
                    'result_snippet':'Nacre announces a desktop search preview.', 'discovered_via_query':'Nacre release'}]
    def validate(self,sources=None,raw=None,hits=None):
        return validate_resolution(raw or self.raw,sources or [],self.choice,
            discoveries=self.hits if hits is None else hits,authorities=self.cfg['resolution_authorities'])
    def test_discovery_alone_resolves_without_quote(self):
        r=self.validate();e=r['evidence'][0]
        self.assertEqual(r['status'],'RESOLVED');self.assertEqual(e['acquisition_state'],'DISCOVERED')
        self.assertNotIn('quote',e);self.assertFalse(e['fetched']);self.assertEqual(e['verified_passage_count'],0)
        self.assertEqual(r['credible_source_ids'],[e['evidence_id']])
    def test_fetched_exact_passage(self):
        r=self.validate([self.source]);self.assertEqual(r['status'],'RESOLVED')
        self.assertEqual(r['evidence'][0]['acquisition_state'],'VERIFIED_PASSAGE')
    def test_fetched_bad_quote_is_not_verified(self):
        self.raw['evidence'][0]['quote']='Invented quote that is not present anywhere on the fetched page.'
        r=self.validate([self.source]);self.assertEqual(r['evidence'][0]['acquisition_state'],'FETCHED')
        self.assertNotIn('quote',r['evidence'][0])
    def test_model_url_without_discovery_cannot_resolve(self):
        self.assertEqual(self.validate(hits=[])['status'],'UNRESOLVED')
    def test_competitor_only_cannot_resolve(self):
        self.choice['competitor_references']=[{'url':self.source['url'],'title':'Nacre preview'}]
        self.assertEqual(self.validate()['status'],'UNRESOLVED')
    def test_weak_event_partial(self):
        self.raw['evidence'][0]['indicates_event']=False
        self.assertEqual(self.validate()['status'],'PARTIALLY_RESOLVED')
    def test_same_owner_once(self):
        self.raw['evidence'].append(dict(self.raw['evidence'][0],url='https://docs.nacre.example/products/desktop-search'))
        self.hits.append(dict(self.hits[0],url=self.raw['evidence'][1]['url']))
        r=self.validate();self.assertEqual(len(r['credible_source_ids']),2);self.assertEqual(r['independent_owner_count'],1)
    def test_contradiction_blocks(self):
        self.raw['evidence'][0]['contradicts_event']=True
        r=self.validate();self.assertEqual(r['status'],'UNRESOLVED');self.assertEqual(r['decision_inputs']['contradiction_count'],1)
    def test_model_status_and_fractional_score_not_binding(self):
        self.raw.update(resolvability_score=.97,status='UNRESOLVED')
        self.assertEqual(self.validate()['status'],'RESOLVED')
    def test_untrusted_domain_label_not_authority(self):
        self.raw['evidence'][0]['url']='https://nacre.example.evil.test/desktop-search'
        self.hits[0]['url']=self.raw['evidence'][0]['url']
        self.assertEqual(self.validate()['status'],'UNRESOLVED')
    def test_fetch_failure_keeps_discovery(self):
        p=Mock();p.resolve_story.return_value=(self.raw,self.hits);p.fetch.side_effect=ProviderFailure('not readable')
        r,s=StoryResolutionGate().resolve(self.choice,p,Budget(self.cfg,offline=True),self.cfg)
        self.assertEqual(r['status'],'RESOLVED');self.assertEqual(s,[])
        self.assertIn('SOURCE_FETCH_PARTIAL_FAILURE',r['warnings']);self.assertEqual(p.fetch.call_count,1)
    def test_transient_fetch_retry_once(self):
        p=Mock();p.resolve_story.return_value=(self.raw,self.hits+[dict(self.hits[0],url=self.source['url']+'?utm_source=x')])
        p.fetch.side_effect=[TimeoutError(),SourceRecord(**self.source)]
        r,s=StoryResolutionGate().resolve(self.choice,p,Budget(self.cfg,offline=True),self.cfg)
        self.assertEqual(r['status'],'RESOLVED');self.assertEqual(p.fetch.call_count,2)
        self.assertEqual(len(s),1);self.assertTrue(r['failures'][0]['transient'])
    def test_full_research_searches_before_fetch_and_synthesis(self):
        p=Mock();p.fetch.return_value=SourceRecord(**self.source);p.search.return_value=[{'url':self.source['url'],'authority_score':80,'relevance_score':100,'freshness_score':100}]
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.bundle['as_of']);plan['story_resolution']=self.validate()
        synth=FixtureResearchSynthesizer(self.bundle)
        # Stop after synthesis; assert that actual fetched text, never a discovery snippet, reaches synthesis.
        synth.synthesize=Mock(side_effect=ProviderFailure('test stops at synthesis'))
        packet,sources,out=collect(p,synth,plan,self.choice,Budget(self.cfg,offline=True))
        p.search.assert_called_once();p.fetch.assert_called_once();self.assertEqual(sources[0]['text'],self.source['text'])
        self.assertIsNone(packet)
    def test_failed_full_research_fetch_does_not_synthesize_discovery(self):
        p=Mock();p.fetch.side_effect=ProviderFailure('unavailable');p.search.return_value=[];synth=Mock()
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.bundle['as_of']);plan['story_resolution']=self.validate()
        packet,sources,out=collect(p,synth,plan,self.choice,Budget(self.cfg,offline=True))
        self.assertEqual(sources,[]);self.assertIsNone(packet);synth.synthesize.assert_not_called()
    def test_replay_preserves_failure_and_does_not_invent_discovery(self):
        with tempfile.TemporaryDirectory() as d:
            self.raw.update(status='UNRESOLVED',failures=[{'stage':'story_resolution_fetch','error':'ProviderFailure'}])
            for name,value in [('story_resolution',self.raw),('sources',[self.source]),('idea',self.choice)]:
                Path(d,name+'.json').write_text(json.dumps(value))
            r=replay(d,self.cfg)
            self.assertEqual(r['status'],'RESOLVED');self.assertIn('SOURCE_FETCH_PARTIAL_FAILURE',r['warnings'])
            self.assertEqual(r['replay']['model_calls'],0)

    def test_secondary_authority_is_configured_not_model_asserted(self):
        self.cfg['resolution_authorities']={'nacre.example':{'owner':'Independent News','authority_type':'REPUTABLE_SECONDARY'}}
        r=self.validate();self.assertEqual(r['status'],'RESOLVED')
        self.assertEqual(r['evidence'][0]['source_owner'],'Independent News')

    def test_two_transient_errors_exhaust_one_retry(self):
        p=Mock();p.resolve_story.return_value=(self.raw,self.hits);p.fetch.side_effect=TimeoutError()
        r,s=StoryResolutionGate().resolve(self.choice,p,Budget(self.cfg,offline=True),self.cfg)
        self.assertEqual(p.fetch.call_count,2);self.assertEqual(r['status'],'RESOLVED');self.assertEqual(s,[])

    def test_full_research_rejects_injected_discovery_text(self):
        p=Mock();p.search.return_value=[];synth=Mock()
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.bundle['as_of'])
        packet,sources,out=collect(p,synth,plan,self.choice,Budget(self.cfg,offline=True),
            initial_sources=[dict(self.source,acquisition_state='DISCOVERED')])
        self.assertEqual(sources,[]);synth.synthesize.assert_not_called()
        self.assertEqual(out['excluded_sources'][0]['reason'],'UNFETCHED_DISCOVERY')

    def test_numeric_confidence_does_not_override_identity_evidence(self):
        for score in (float('nan'),float('inf'),-1,101,'97'):
            with self.subTest(score=score):
                self.raw['resolvability_score']=score
                self.assertNotEqual(self.validate()['status'],'RESOLVED')

    def test_adapter_preserves_only_actual_tool_metadata(self):
        from tech_uncovered.scripting.providers.openai_live import WebResearchProvider
        response={'output':[
            {'type':'web_search_call','action':{'queries':['actual query'], 'sources':[{'url':self.source['url'],'title':'Actual tool title','snippet':'Actual tool snippet'}]}},
            {'type':'message','content':[{'type':'output_text','text':json.dumps(self.raw)}]}]}
        budget=Budget(self.cfg,offline=True)
        model=OpenAIModel('unused',self.cfg,budget)
        provider=WebResearchProvider(model,self.cfg,budget,self.bundle['as_of'])
        with patch.object(OpenAIModel,'request',return_value=response):
            raw,hits=provider.resolve_story(self.choice,self.cfg)
        self.assertEqual(hits[0]['result_snippet'],'Actual tool snippet')
        self.assertEqual(hits[0]['result_title'],'Actual tool title')
        self.assertEqual(hits[0]['discovered_via_query'],'actual query')
        self.assertNotIn('quote',hits[0])
