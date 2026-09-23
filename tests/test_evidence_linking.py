import copy
import unittest
from unittest.mock import patch
from tech_uncovered.scripting.claims import validate_packet
from tech_uncovered.scripting.pivots import recommend_pivot


def inputs():
    subject='Nacre One'
    text=('Nacre One is an API model. Tools Tools supported by this model when using the Responses API. '
          'Computer use Supported MCP Supported Modalities Text Input and output Image Input only '
          'Audio Not supported Video Not supported Features Fine-tuning Not supported '
          '24,000 context window 2,000 max output tokens Text tokens Per 1M tokens Input $2.00 '
          'Cached input $0.20 Output $8.00')
    source=dict(source_id='s1',text=text,title='Nacre One Model',url='https://nacre.example/model',
                authority_type='FIRST_PARTY',source_owner='Nacre',retrieved_at='2026-09-20T00:00:00+00:00',publication_date=None)
    kinds=['IDENTITY_EVENT','CAPABILITY','CONSTRAINT','SPECIFICATION','RESEARCH_QUESTION','RESEARCH_QUESTION']
    words=['Documentation lists Nacre One but no dated release.',
           'Nacre documents computer use for Nacre One in the Responses API.',
           'Audio and video unsupported; fine-tuning not supported.',
           'Context and input price $2.00.',
           'Documentation lists tools, token limits and constraints.', '']
    claims=[dict(claim_id=str(i),claim_type=k,text=w,supported_wording=w,status='UNVERIFIED',materiality='CRITICAL',
                 evidence_ids=[],passages=[],limitations=[]) for i,(k,w) in enumerate(zip(kinds,words))]
    cats=['IDENTITY_EVENT','PRIMARY_DOCUMENTATION','COMPARISON_ALTERNATIVE','COMPARISON_CRITERION']
    plan=dict(canonical_topic=subject,planned_at='2026-09-20T00:00:00+00:00',freshness_requirement={'window_days':30},
              requirement_queue=[dict(requirement_id=c,category=c) for c in cats],requirements=[dict(requirement_id=c,text=c) for c in cats],comparison_required=True)
    raw=dict(claims=claims,core_claim_ids=['0','1'],freshness={'established':False},canonical_story_resolved=True,
             remaining_questions_material=True,source_assessments=[dict(source_id='s1',source_type='DOCUMENTATION',
             primary_or_secondary='PRIMARY',credible_for_claim_ids=[str(i) for i in range(5)],rationale='Primary product documentation')],
             requirement_resolutions=[dict(requirement_id=c,claim_ids=ids,rationale='Scoped evidence') for c,ids in zip(cats,[['0'],['1','2','3','4'],['5'],['5']])])
    selected={'idea':{'idea_id':'i','proposed_angle':'comparison'}}
    outcome=dict(stop_reason='ANGLE_UNSUPPORTED',requirements_attempted=cats,unused_search_budget=0)
    return raw,[source],plan,selected,outcome


class EvidenceLinkingTests(unittest.TestCase):
    def setUp(self):
        for target in ('socket.create_connection','socket.getaddrinfo','tech_uncovered.scripting.providers.openai_live.OpenAIModel.request'):
            guard=patch(target,side_effect=AssertionError('Offline test: live calls forbidden'));guard.start();self.addCleanup(guard.stop)
        self.raw,self.sources,self.plan,self.selected,self.outcome=inputs()
    def packet(self):return validate_packet(self.raw,self.sources,self.plan,self.selected)
    def test_links_and_exact_offsets(self):
        p=self.packet()
        for c in p['claims'][:5]:
            self.assertEqual(c['evidence_ids'],['s1'])
            for e in c['passages']:
                self.assertIn(c['claim_id'],e['claim_ids'])
                self.assertEqual(e['text'],self.sources[0]['text'][e['start_offset']:e['end_offset']])
                self.assertIn(e['support_type'],('DIRECT','PARTIAL','CONTRADICTING'))
    def test_scoped_claim_verified_with_unresolved_comparison(self):
        p=self.packet();self.assertEqual(p['claims'][1]['status'],'VERIFIED');self.assertFalse(p['comparison_supported'])
        self.assertEqual(p['claims'][1]['verification_scope'],'SUPPORTED_WORDING_ONLY')
    def test_requirements_independent(self):
        p=self.packet();states={r['category']:r['status'] for r in p['requirement_statuses']}
        self.assertEqual(states,dict(IDENTITY_EVENT='PARTIALLY_RESOLVED',PRIMARY_DOCUMENTATION='RESOLVED',COMPARISON_ALTERNATIVE='UNRESOLVED',COMPARISON_CRITERION='UNRESOLVED'))
        self.assertEqual(p['resolved_requirement_ids'],['PRIMARY_DOCUMENTATION'])
    def test_partial_research(self):self.assertEqual(self.packet()['research_status'],'PARTIAL')
    def test_pivot_derived_no_alternative_or_script(self):
        p=self.packet();pivot=recommend_pivot(p,self.plan,self.selected,self.outcome)
        self.assertEqual(pivot['status'],'ANGLE_PIVOT_RECOMMENDED');self.assertIn('Nacre One',pivot['recommended_angle'])
        self.assertFalse(pivot['pivot_requires_new_research']);self.assertEqual(p['research_status'],'PARTIAL')
        self.assertNotIn('GPT',pivot['recommended_angle']);self.assertNotIn('script',p)
    def test_pivot_does_not_use_model_safe_angle(self):
        self.raw['safe_angle']='Invented Rival is better';p=self.packet()
        self.assertNotIn('Invented',recommend_pivot(p,self.plan,self.selected,self.outcome)['recommended_angle'])
    def test_no_pivot_before_exhaustion(self):
        self.outcome['unused_search_budget']=1
        self.assertIsNone(recommend_pivot(self.packet(),self.plan,self.selected,self.outcome))
    def test_no_pivot_without_all_comparison_attempts(self):
        self.outcome['requirements_attempted']=[]
        self.assertIsNone(recommend_pivot(self.packet(),self.plan,self.selected,self.outcome))
    def test_no_pivot_without_three_verified_claims(self):
        p=self.packet();p['claims'][1]['status']='UNVERIFIED'
        self.assertIsNone(recommend_pivot(p,self.plan,self.selected,self.outcome))
    def test_no_pivot_on_contradiction(self):
        p=self.packet();p['research_status']='CONTRADICTED'
        self.assertIsNone(recommend_pivot(p,self.plan,self.selected,self.outcome))
    def test_no_authority_no_repair(self):
        self.sources[0]['authority_type']='COMMUNITY';p=self.packet()
        self.assertTrue(all(c['status']=='UNVERIFIED' for c in p['claims']))
    def test_no_fetched_text_no_evidence(self):
        self.sources[0]['text']='';self.assertEqual(self.packet()['research_status'],'INSUFFICIENT')
    def test_confidence_and_rationale_not_evidence(self):
        self.raw['claims'][5].update(confidence=1,rationale='Definitely supported',supported_wording='A rival beats this model')
        self.assertEqual(self.packet()['claims'][5]['status'],'UNVERIFIED')
    def test_wrong_subject_cannot_repair(self):
        self.sources[0]['title']='Other model';self.assertEqual(self.packet()['research_status'],'INSUFFICIENT')
    def test_api_scope_required_for_tool(self):
        self.sources[0]['text']=self.sources[0]['text'].replace('Tools supported by this model when using the Responses API.','')
        self.assertEqual(self.packet()['claims'][1]['status'],'UNVERIFIED')
    def test_repair_does_not_verify_wrong_original_values(self):
        self.raw['claims'][3]['supported_wording']='Context and input price $999.'
        c=self.packet()['claims'][3];self.assertIn('$999',c['original_supported_wording']);self.assertNotIn('$999',c['supported_wording'])
        self.assertEqual(c['verification_scope'],'SUPPORTED_WORDING_ONLY')
    def test_news_requires_dated_evidence(self):
        self.assertFalse(self.packet()['freshness']['established'])
    def test_evergreen_documentation_without_news_date(self):
        self.plan['freshness_requirement']['mode']='EVERGREEN';p=self.packet()
        self.assertTrue(p['freshness']['established']);self.assertFalse(p['freshness_assessments']['NEWS_FRESHNESS']['established'])
        self.assertFalse(p['comparison_supported']);self.assertEqual(p['research_status'],'PARTIAL')
    def test_stale_observation_blocks_currentness_and_pivot(self):
        self.sources[0]['retrieved_at']='2020-01-01T00:00:00+00:00';p=self.packet()
        self.assertFalse(p['freshness_assessments']['EVERGREEN']['established'])
        self.assertIsNone(recommend_pivot(p,self.plan,self.selected,self.outcome))
    def test_roundtrip_preserves_passage_ids(self):
        p=self.packet();again=validate_packet(copy.deepcopy(p),self.sources,self.plan,self.selected)
        self.assertEqual(p['evidence_passages'],again['evidence_passages'])
