import copy
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.error import HTTPError
from tech_uncovered.database import Database
from tech_uncovered.cli import main
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.resolution import StoryResolutionGate,RESOLUTION_EXAMPLE,validate_resolution,assess_researchability
from tech_uncovered.scripting.sources import canonical_url,topic_relevance
from tech_uncovered.scripting.selection import select_ideas
from tech_uncovered.scripting.planning import BoundedResearchPlanner
from tech_uncovered.scripting.research import collect
from tech_uncovered.scripting.providers.fixtures import FixtureResearchProvider,FixtureResearchSynthesizer
from tech_uncovered.scripting.providers.openai_live import OpenAIModel,WebResearchProvider
from tests.script_helpers import ROOT,fixture,config,selected,execute


class StoryResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.db';self.db=Database(self.path)
        self.choice=selected(self.db);self.bundle=fixture();self.cfg=config()
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def resolve(self,bundle=None):
        b=bundle or self.bundle
        return StoryResolutionGate().resolve(self.choice,FixtureResearchProvider(b),Budget(self.cfg,offline=True),self.cfg)
    def test_known_fixture_entity_passes(self):
        r,s=self.resolve();self.assertEqual(r['status'],'RESOLVED');self.assertEqual(r['credible_source_ids'],[r['evidence'][0]['evidence_id']]);self.assertEqual(r['evidence'][0]['research_source_id'],'src-nacre')
    def test_vague_story_stops_before_synthesis(self):
        b=copy.deepcopy(self.bundle);b['story_resolution']=copy.deepcopy(RESOLUTION_EXAMPLE)
        synth=Mock();synth.name="test-synth";synth.version="1"
        with patch('socket.create_connection',side_effect=AssertionError('No network')):
            result=execute(self.db,b,choice=self.choice,synthesizer=synth)
        synth.synthesize.assert_not_called();self.assertIsNone(result['packet']);self.assertIsNone(result['draft'])
        self.assertEqual(result['readiness']['status'],'RESEARCH_REQUIRED')
        self.assertEqual(result['research_outcome']['stop_reason'],'STORY_UNRESOLVED')
        for name in ('full_research_cost','script_generation_cost','fact_check_cost','quality_review_cost'):
            self.assertEqual(result['cost'][name]['estimated_cost_usd'],0)
    def test_competitor_only_fails(self):
        b=copy.deepcopy(self.bundle);b['sources'][0]['url']=self.choice['competitor_references'][0]['url'];b['story_resolution']['evidence'][0]['url']=b['sources'][0]['url']
        self.assertEqual(self.resolve(b)[0]['status'],'UNRESOLVED')
    def test_repost_fails(self):
        b=copy.deepcopy(self.bundle);b['story_resolution']['evidence'][0]['independent_of_competitor']=False
        self.assertEqual(self.resolve(b)[0]['status'],'UNRESOLVED')
    def test_invented_quote_not_verified_but_identity_can_resolve(self):
        b=copy.deepcopy(self.bundle);b['story_resolution']['evidence'][0]['quote']='Nacre claims this invented sentence which never appears in the page.'
        result=self.resolve(b)[0]
        self.assertEqual(result['status'],'RESOLVED')
        self.assertNotIn('quote',result['evidence'][0])
        self.assertEqual(result['evidence'][0]['verified_passage_count'],0)
    def test_entity_without_event_fails(self):
        b=copy.deepcopy(self.bundle);b['story_resolution']['alleged_event']=''
        self.assertEqual(self.resolve(b)[0]['status'],'PARTIALLY_RESOLVED')
    def test_partial_resolution_never_enters_full_research(self):
        b=copy.deepcopy(self.bundle);b['story_resolution']['status']='PARTIALLY_RESOLVED';b['story_resolution']['resolvability_score']=50
        r=execute(self.db,b,choice=self.choice)
        self.assertEqual(r['readiness']['status'],'RESEARCH_REQUIRED');self.assertIsNone(r['packet'])
    def test_tracking_and_query_variants_collapse(self):
        urls=['https://EXAMPLE.com/story/?utm_source=x#one','https://example.com/story?fbclid=x','https://example.com/story?edition=alternate']
        self.assertEqual(len({canonical_url(u) for u in urls}),1)
    def test_gate_max_two_unique_fetch_attempts(self):
        provider=FixtureResearchProvider(self.bundle)
        hits=[{'url':'https://x.example/'+str(i)} for i in range(5)]
        with patch.object(provider,'resolve_story',return_value=(self.bundle['story_resolution'],hits)),patch.object(provider,'fetch',side_effect=ValueError('unavailable')) as fetch:
            StoryResolutionGate().resolve(self.choice,provider,Budget(self.cfg,offline=True),self.cfg)
        self.assertEqual(fetch.call_count,2)
    def test_gate_duplicate_not_refetched(self):
        provider=FixtureResearchProvider(self.bundle);url=self.bundle['sources'][0]['url']
        hits=[{'url':url},{'url':url+'?utm_source=duplicate'}]
        with patch.object(provider,'resolve_story',return_value=(self.bundle['story_resolution'],hits)),patch.object(provider,'fetch',wraps=provider.fetch) as fetch:
            r,s=StoryResolutionGate().resolve(self.choice,provider,Budget(self.cfg,offline=True),self.cfg)
        self.assertEqual(fetch.call_count,1);self.assertEqual(s[0]['canonical_url'],url);self.assertEqual(s[0]['retrieved_url'],url)
    def test_generic_essay_rejected(self):
        source=dict(self.bundle['sources'][0],title='The future of AI',text='AI is changing the world. Tomorrow will be different.')
        self.assertEqual(topic_relevance(source,self.bundle['story_resolution']),0)
    def test_wrong_date_rejected(self):
        source=dict(self.bundle['sources'][0],publication_date='2020-01-01T00:00:00+00:00')
        self.assertLess(topic_relevance(source,self.bundle['story_resolution']),70)
    def test_wrong_product_rejected(self):
        source=dict(self.bundle['sources'][0],title='Nacre mobile app',text='Nacre released a mobile messaging app.')
        self.assertLess(topic_relevance(source,self.bundle['story_resolution']),70)
    def test_researchability_prefers_concrete_context(self):
        vague=copy.deepcopy(self.choice);vague['idea'].update(story_context=[],risk_flags=['CONTEXT_LIMITED'])
        concrete=copy.deepcopy(self.choice);concrete['idea'].update(risk_flags=[],story_context=[{'canonical_subject':'Nacre search preview','entities':['Nacre'],'core_event':'Desktop preview released','confidence':.9}])
        self.assertGreater(assess_researchability(concrete)['researchability_score'],assess_researchability(vague)['researchability_score'])
    def test_selection_tiebreak_preserves_idea_score(self):
        original=self.choice['idea'];original['story_context']=[]
        with self.db.connection:self.db.connection.execute('UPDATE idea_candidates SET payload=?',(json.dumps(original),))
        better=copy.deepcopy(original);better.update(idea_id='idea-researchable',idea_score=original['idea_score']-2,story_context=[{'canonical_subject':'Nacre local search preview','entities':['Nacre'],'core_event':'Preview released','confidence':.9}],risk_flags=[])
        with self.db.connection:self.db.connection.execute('INSERT INTO idea_candidates VALUES (?,?,?,?,?,?)',(better['intelligence_run_id'],better['idea_id'],0,'CLEAR',better['category'],json.dumps(better)))
        result=select_ideas(self.db,better['intelligence_run_id'],top=1,prefer_researchable=True)[0]
        self.assertEqual(result['idea']['idea_id'],better['idea_id']);self.assertEqual(result['idea']['idea_score'],better['idea_score'])
    def test_preview_zero_network_model_calls_and_database_unchanged(self):
        before=self.path.read_bytes()
        with patch('socket.create_connection',side_effect=AssertionError('Network')),patch.object(OpenAIModel,'request',side_effect=AssertionError('Model')),redirect_stdout(io.StringIO()) as out:
            code=main(['script','--preview','--db',str(self.path),'--intelligence-run-id',self.choice['intelligence_run_id']])
        self.assertEqual(code,0);self.assertEqual(before,self.path.read_bytes());self.assertIn('researchability_score',out.getvalue())
    def live_provider(self,budget,transport):
        provider=WebResearchProvider(OpenAIModel('fake-key',self.cfg,budget,transport),self.cfg,budget,self.bundle['as_of'])
        provider.fetch=FixtureResearchProvider(self.bundle).fetch
        return provider
    def response(self):
        return {'status':'completed','usage':{'input_tokens':2000,'output_tokens':700},'output':[
            {'type':'web_search_call','action':{'sources':[{'url':self.bundle['sources'][0]['url']}]}},
            {'type':'message','content':[{'type':'output_text','text':json.dumps(self.bundle['story_resolution'])}]}]}
    def test_live_preflight_one_call_one_search_under_budget(self):
        payloads=[];budget=Budget(self.cfg)
        def transport(p):payloads.append(p);return self.response()
        provider=self.live_provider(budget,transport)
        with budget.stage('story_resolution_cost'):r,s=StoryResolutionGate().resolve(self.choice,provider,budget,self.cfg)
        self.assertEqual(r['status'],'RESOLVED');self.assertEqual(len(payloads),1);self.assertEqual(payloads[0]['max_tool_calls'],1)
        self.assertEqual(payloads[0]['max_output_tokens'],1200);self.assertLess(budget.record.story_resolution_cost['estimated_cost_usd'],.08)
        self.assertEqual(budget.record.full_research_cost['estimated_cost_usd'],0)
    def test_preflight_cost_limit_prevents_dispatch(self):
        cfg=dict(self.cfg,preflight_max_cost_usd=.000001);budget=Budget(cfg);transport=Mock()
        r,_=StoryResolutionGate().resolve(self.choice,self.live_provider(budget,transport),budget,cfg)
        self.assertEqual(r['status'],'UNRESOLVED');transport.assert_not_called()
    def test_preflight_timeout_prevents_fetch_or_full_research(self):
        clock=[0];budget=Budget(self.cfg,clock=lambda:clock[0])
        def transport(p):clock[0]=46;return self.response()
        provider=self.live_provider(budget,transport);provider.fetch=Mock()
        r,_=StoryResolutionGate().resolve(self.choice,provider,budget,self.cfg)
        self.assertEqual(r['status'],'UNRESOLVED');provider.fetch.assert_not_called();self.assertEqual(budget.record.model_calls,1)
    def test_preflight_no_retry_on_429(self):
        budget=Budget(self.cfg);transport=Mock(side_effect=HTTPError('https://api.example',429,'rate',{},None))
        r,_=StoryResolutionGate().resolve(self.choice,self.live_provider(budget,transport),budget,self.cfg)
        self.assertEqual(r['status'],'UNRESOLVED');self.assertEqual(transport.call_count,1)
    def test_unknown_usage_visible_in_resolution_cost(self):
        budget=Budget(self.cfg);provider=self.live_provider(budget,lambda p:{'output':[]})
        with budget.stage('story_resolution_cost'):r,_=StoryResolutionGate().resolve(self.choice,provider,budget,self.cfg)
        self.assertGreater(budget.record.story_resolution_cost['estimated_cost_upper_bound_usd'],0);self.assertEqual(budget.record.full_research_cost['estimated_cost_usd'],0)
    def test_full_research_deduplicates_before_synthesis(self):
        provider=FixtureResearchProvider(self.bundle);url=self.bundle['sources'][0]['url'];hits=provider.search('x',question_id='x');hits+=[dict(hits[0],url=url+'?utm_campaign=x')]
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.bundle['as_of'])
        b=copy.deepcopy(self.bundle);b['packet']['remaining_questions_material']=True
        synth=FixtureResearchSynthesizer(b)
        with patch.object(provider,'search',return_value=hits),patch.object(provider,'fetch',wraps=provider.fetch) as fetch,patch.object(synth,'synthesize',wraps=synth.synthesize) as synthesis:
            packet,sources,outcome=collect(provider,synth,plan,self.choice,Budget(self.cfg,offline=True))
        self.assertEqual(fetch.call_count,1);self.assertEqual(synthesis.call_count,1)
    def test_full_research_off_topic_stops_without_synthesis(self):
        b=copy.deepcopy(self.bundle);b['sources'][0].update(title='Generic AI future',text='Technology will change everything one day.')
        provider=FixtureResearchProvider(b);synth=Mock();plan=BoundedResearchPlanner().plan(self.choice,self.cfg,b['as_of']);plan['story_resolution']=self.bundle['story_resolution']
        packet,sources,out=collect(provider,synth,plan,self.choice,Budget(self.cfg,offline=True))
        synth.synthesize.assert_not_called();self.assertEqual(out['stop_reason'],'NO_NEW_RELEVANT_EVIDENCE');self.assertEqual(out['logical_search_calls'],2)
        self.assertEqual(sources,[]);self.assertTrue(out['excluded_sources'])
    def test_unsupported_angle_stops_after_first_synthesis(self):
        b=copy.deepcopy(self.bundle);b['packet']['early_stop_reason']='ANGLE_UNSUPPORTED'
        synth=FixtureResearchSynthesizer(b)
        with patch.object(synth,'synthesize',wraps=synth.synthesize) as call:
            r=execute(self.db,b,choice=self.choice,synthesizer=synth)
        self.assertEqual(call.call_count,1);self.assertEqual(r['readiness']['status'],'RESEARCH_REQUIRED');self.assertIsNone(r['draft'])
    def test_resolution_persisted_without_schema_change(self):
        r=execute(self.db,self.bundle,choice=self.choice)
        row=self.db.connection.execute('SELECT outcome FROM research_runs_v3 WHERE research_run_id=?',(r['research_run_id'],)).fetchone()
        self.assertEqual(json.loads(row[0])['story_resolution']['status'],'RESOLVED')
        self.assertEqual(self.db.connection.execute('PRAGMA user_version').fetchone()[0],4)
    def test_copied_title_is_not_independent_event_evidence(self):
        b=copy.deepcopy(self.bundle);title=self.choice['competitor_references'][0]['title']
        b['story_resolution']['evidence'][0]['quote']=title+' was covered by a competitor this week.'
        b['sources'][0]['text']+=' '+b['story_resolution']['evidence'][0]['quote']
        result=self.resolve(b)[0]
        self.assertEqual(result['status'],'RESOLVED')
        self.assertNotIn('quote',result['evidence'][0])
        self.assertEqual(result['evidence'][0]['verified_passage_count'],0)
    def test_generic_identity_cannot_pass_with_high_score(self):
        b=copy.deepcopy(self.bundle);b['story_resolution'].update(canonical_subject='ai',named_entities=['ai'],alleged_event='new ai',resolvability_score=100)
        self.assertEqual(self.resolve(b)[0]['status'],'UNRESOLVED')
    def test_undiscovered_url_not_fetched(self):
        response=self.response();response['output'][0]['action']['sources']=[]
        budget=Budget(self.cfg);provider=self.live_provider(budget,lambda p:response);provider.fetch=Mock()
        r,_=StoryResolutionGate().resolve(self.choice,provider,budget,self.cfg)
        self.assertEqual(r['status'],'UNRESOLVED');provider.fetch.assert_not_called()
    def test_split_costs_sum_to_total(self):
        budget=Budget(self.cfg)
        for name in ('story_resolution_cost','full_research_cost','script_generation_cost','fact_check_cost','quality_review_cost'):
            with budget.stage(name):
                reservation=budget.reserve(100)
                budget.settle(reservation,{'usage':{'input_tokens':100,'output_tokens':50},'output':[]},name)
        actual=budget.record.estimated_model_cost_usd+budget.record.estimated_search_cost_usd
        self.assertAlmostEqual(actual,sum(getattr(budget.record,k)['estimated_cost_usd'] for k in ('story_resolution_cost','full_research_cost','script_generation_cost','fact_check_cost','quality_review_cost')))
