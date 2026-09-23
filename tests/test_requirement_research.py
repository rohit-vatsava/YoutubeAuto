import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from tech_uncovered.database import Database
from tech_uncovered.scripting.planning import BoundedResearchPlanner
from tech_uncovered.scripting.requirements import prepare,next_query,query_key
from tech_uncovered.scripting.research import collect
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.costs import Budget
from tech_uncovered.scripting.providers.fixtures import FixtureResearchProvider,FixtureResearchSynthesizer
from tech_uncovered.scripting.reports import export
from tests.script_helpers import selected,config,fixture,execute


class RequirementResearchTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection','socket.getaddrinfo','tech_uncovered.scripting.providers.openai_live.OpenAIModel.request'):
            p=patch(target,side_effect=AssertionError('No live calls'));p.start();self.addCleanup(p.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database(Path(self.tmp.name)/'test.db');self.addCleanup(self.db.close)
        self.choice=selected(self.db);self.bundle=fixture();self.cfg=config()
        self.choice['idea'].update(proposed_angle='comparison',transformation='comparison',
            required_research=['Choose and verify a relevant alternative and a like-for-like comparison criterion.',
                               'Validate the underlying subject and development represented by this video.'])
        self.plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.bundle['as_of'])
        self.plan['story_resolution']=dict(self.bundle['story_resolution'],evidence=[{
            'url':self.bundle['sources'][0]['url'],'domain':'nacre.example','source_authority_type':'FIRST_PARTY'}])
        prepare(self.plan,self.choice)
    def research(self,provider=None,bundle=None,initial=True):
        b=copy.deepcopy(bundle or self.bundle);b['packet']['early_stop_reason']='ANGLE_UNSUPPORTED'
        p=provider or FixtureResearchProvider(b);s=FixtureResearchSynthesizer(b)
        return collect(p,s,self.plan,self.choice,Budget(self.cfg,offline=True),initial_sources=b['sources'] if initial else None)
    def test_inherited_source_does_not_suppress_comparison_discovery(self):
        p,s,out=self.research()
        self.assertGreaterEqual(out['logical_search_calls'],3)
        self.assertGreaterEqual(out['search_attempts_for_angle'],1)
        self.assertEqual(out['stop_reason'],'ANGLE_UNSUPPORTED')
        self.assertTrue(out['angle_unsupported_reason'])
    def test_angle_failure_preserves_verified_partial_research(self):
        p,_,out=self.research()
        self.assertEqual(out['stop_reason'],'ANGLE_UNSUPPORTED')
        self.assertEqual(p['research_status'],'PARTIAL')
        self.assertTrue(p['verified_claims'])

    def test_search_before_any_synthesis(self):
        events=[];provider=FixtureResearchProvider(self.bundle);search=provider.search
        provider.search=lambda *a,**kw:events.append('search') or search(*a,**kw)
        synth=FixtureResearchSynthesizer(self.bundle);synthesis=synth.synthesize
        synth.synthesize=lambda *a:events.append('synthesis') or synthesis(*a)
        collect(provider,synth,self.plan,self.choice,Budget(self.cfg,offline=True),initial_sources=self.bundle['sources'])
        self.assertEqual(events[0],'search')
    def test_failed_primary_is_not_refetched(self):
        url=self.bundle['sources'][0]['url'];self.plan['story_resolution']['failures']=[{'url':url,'stage':'story_resolution_fetch'}]
        p=FixtureResearchProvider(self.bundle);p.fetch=Mock(side_effect=AssertionError('failed URL retried'))
        _,_,out=self.research(p,initial=False)
        p.fetch.assert_not_called()
        self.assertTrue(out['research_searches'][0]['query'].startswith('site:nacre.example'))
        self.assertTrue(any('documentation' in s['query'] for s in out['research_searches']))
    def test_no_invented_alternative(self):
        q=next(q for q in self.plan['requirement_queue'] if q['category']=='COMPARISON_CRITERION')
        packet={'comparison_evidence':{'alternative':'InventedProduct','criterion':'latency'}}
        self.assertNotIn('InventedProduct',next_query(q,0,packet,self.plan['canonical_topic']))
    def test_only_grounded_candidate_refines_query(self):
        q=next(q for q in self.plan['requirement_queue'] if q['category']=='COMPARISON_CRITERION')
        packet={'comparison_candidate_grounded':True,'comparison_evidence':{'alternative':'Fixture Alternative','criterion':'latency'}}
        query=next_query(q,0,packet,self.plan['canonical_topic'])
        self.assertIn('Fixture Alternative',query);self.assertIn('latency',query)
    def test_comparison_criterion_requires_both_sides(self):
        raw=copy.deepcopy(self.bundle['packet']);raw['requirement_resolutions']=[{'requirement_id':r['requirement_id'],
            'claim_ids':[raw['claims'][0]['claim_id']],'rationale':'claimed resolved'} for r in self.plan['requirements']]
        raw['comparison_evidence']={'decision':'select tool','alternative':'InventedProduct','criterion':'latency',
            'conditions':'same test','like_for_like':True,'selection_claim_ids':[raw['claims'][0]['claim_id']],
            'subject_claim_ids':[raw['claims'][0]['claim_id']],'alternative_claim_ids':[raw['claims'][0]['claim_id']],'rationale':'model assertion'}
        packet=validate_packet(raw,self.bundle['sources'],self.plan,self.choice)
        self.assertFalse(packet['comparison_supported']);self.assertFalse(packet['comparison_candidate_grounded'])
        self.assertNotEqual(packet['research_status'],'SUFFICIENT')
    def test_cluster_generic_claims_deduplicated_with_lineage(self):
        self.choice['idea']['story_context']=[{'uncertain_claims':[{'claim_id':str(i),
            'text':'Validate the underlying subject and development represented by this video.'}]} for i in range(4)]
        plan=BoundedResearchPlanner().plan(self.choice,self.cfg,self.bundle['as_of'])
        inherited=[c for c in plan['claims_to_verify'] if c.get('origin_claim_ids')]
        self.assertEqual(len(inherited),1);self.assertEqual(len(inherited[0]['origin_claim_ids']),4)
        self.assertTrue(inherited[0]['text'].startswith('Was '))
    def test_prepare_idempotent(self):
        old=copy.deepcopy(self.plan);prepare(self.plan,self.choice)
        self.assertEqual(old,self.plan)
    def test_global_and_requirement_limits(self):
        _,_,out=self.research()
        self.assertLessEqual(out['logical_search_calls'],4)
        self.assertTrue(all(n<=2 for n in out['searches_by_requirement'].values()))
        self.assertEqual(out['unused_search_budget'],4-out['logical_search_calls'])
    def test_search_records_complete(self):
        _,_,out=self.research()
        for entry in out['research_searches']:
            self.assertTrue(set(['search_id','requirement_ids','query','reason','results_returned','selected_results',
                                 'rejected_results','search_cost_usd','timestamp'])<=set(entry))
            self.assertEqual(entry['search_cost_usd'],0)
    def test_semantic_query_normalization(self):
        self.assertEqual(query_key('Example official announcement docs'),query_key('docs Example official release'))
    def test_sufficient_noncomparison_early_stop(self):
        choice=copy.deepcopy(self.choice)
        choice['idea'].update(proposed_angle='mechanism',transformation='mechanism',required_research=['Establish the release and its actual privacy boundary'])
        plan=BoundedResearchPlanner().plan(choice,self.cfg,self.bundle['as_of'])
        p,s,out=collect(FixtureResearchProvider(self.bundle),FixtureResearchSynthesizer(self.bundle),plan,choice,Budget(self.cfg,offline=True))
        self.assertEqual(out['logical_search_calls'],1);self.assertEqual(out['stop_reason'],'EVIDENCE_SUFFICIENT')
    def test_search_provenance_persisted_in_database_and_report(self):
        choice=copy.deepcopy(self.choice)
        choice['idea'].update(proposed_angle='mechanism',transformation='mechanism',required_research=['Establish the release and its actual privacy boundary'])
        result=execute(self.db,self.bundle,choice=choice)
        row=self.db.connection.execute('SELECT outcome FROM research_runs_v3 WHERE research_run_id=?',(result['research_run_id'],)).fetchone()
        self.assertTrue(json.loads(row[0])['research_searches'])
        folder=export(result,Path(self.tmp.name)/'reports')
        self.assertEqual(json.loads((folder/'research_searches.json').read_text()),result['research_outcome']['research_searches'])
    def test_source_budget_cannot_emit_premature_angle_unsupported(self):
        self.plan['max_sources']=1
        _,_,out=self.research()
        self.assertEqual(out['stop_reason'],'SOURCE_LIMIT');self.assertIsNone(out['angle_unsupported_reason'])

    def test_passage_grounded_comparison_can_pass(self):
        raw=copy.deepcopy(self.bundle['packet']);source=copy.deepcopy(self.bundle['sources'][0])
        subject=self.plan['canonical_topic']
        quote=f'{subject} and Fictional Alternative have documented latency under the same fictional test conditions.'
        source['text']+=' '+quote
        claim=raw['claims'][0];claim.update(text=quote,status='VERIFIED',supported_wording=quote,
            evidence_ids=[source['source_id']],passages=[{'source_id':source['source_id'],'quote':quote,'relation':'SUPPORTS'}])
        ids=[claim['claim_id']]
        raw['comparison_evidence']={'decision':'Choose a tool','alternative':'Fictional Alternative','criterion':'latency',
            'conditions':'same fictional test','like_for_like':True,'selection_claim_ids':ids,
            'subject_claim_ids':ids,'alternative_claim_ids':ids,'rationale':'Both measured under the same fictional test'}
        raw['requirement_resolutions']=[{'requirement_id':r['requirement_id'],'claim_ids':ids,'rationale':'Fixture passage supports the question'} for r in self.plan['requirements']]
        packet=validate_packet(raw,[source],self.plan,self.choice)
        self.assertTrue(packet['comparison_candidate_grounded']);self.assertTrue(packet['comparison_supported'])
        q=next(q for q in self.plan['requirement_queue'] if q['category']=='COMPARISON_CRITERION')
        self.assertIn('Fictional Alternative',next_query(q,0,packet,subject))
        raw['comparison_evidence']['alternative_claim_ids']=[]
        self.assertFalse(validate_packet(raw,[source],self.plan,self.choice)['comparison_supported'])

    def test_budget_failure_is_not_angle_unsupported(self):
        from tech_uncovered.scripting.costs import LimitReached
        provider=Mock();provider.search.side_effect=LimitReached('Cost budget cannot fund request')
        _,_,out=self.research(provider)
        self.assertNotEqual(out['stop_reason'],'ANGLE_UNSUPPORTED')
        self.assertIsNone(out['angle_unsupported_reason'])

    def test_full_search_allocation_not_consumed_by_preflight(self):
        from tech_uncovered.scripting.providers.openai_live import WebResearchProvider,OpenAIModel
        from tech_uncovered.scripting.costs import LimitReached
        budget=Budget(self.cfg,offline=True);budget.record.search_calls=1
        provider=WebResearchProvider(OpenAIModel('unused',self.cfg,budget),self.cfg,budget,self.bundle['as_of'])
        with patch.object(OpenAIModel,'request',return_value={'output':[]}) as request:
            for n in range(4):provider.search('query '+str(n),question_id=str(n))
            with self.assertRaises(LimitReached):provider.search('fifth',question_id='fifth')
            self.assertEqual(request.call_count,4)

    def test_secondary_cannot_clear_primary_documentation_requirement(self):
        raw=copy.deepcopy(self.bundle['packet'])
        req=next(q for q in self.plan['requirement_queue'] if q['category']=='PRIMARY_DOCUMENTATION')
        raw['requirement_resolutions'].append({'requirement_id':req['requirement_id'],
            'claim_ids':[raw['claims'][0]['claim_id']],'rationale':'Secondary reporting'})
        for a in raw['source_assessments']:a.update(source_type='NEWS',primary_or_secondary='SECONDARY')
        packet=validate_packet(raw,self.bundle['sources'],self.plan,self.choice)
        self.assertNotIn(req['requirement_id'],packet['resolved_requirement_ids'])

    def test_offline_replay_is_planning_only(self):
        from tech_uncovered.scripting.research_replay import preview
        folder=Path(self.tmp.name)/'replay';folder.mkdir()
        for name,value in [('idea',self.choice),('research_plan',self.plan),
                           ('story_resolution',self.plan['story_resolution']),('research_outcome',{'logical_search_calls':0})]:
            (folder/(name+'.json')).write_text(json.dumps(value))
        before={p.name:p.read_bytes() for p in folder.iterdir()}
        result=preview(folder,self.cfg)
        self.assertEqual(result['network_calls'],0);self.assertEqual(result['model_calls'],0)
        self.assertEqual(len(result['planned_searches']),4)
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
