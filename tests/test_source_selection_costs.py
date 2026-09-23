import copy
import json
import unittest
from unittest.mock import patch
from tech_uncovered.scripting.source_selection import rank_results,score_result,group_url
from tech_uncovered.scripting.authority import classify
from tech_uncovered.scripting.costs import Budget,LimitReached,ProviderFailure
from tech_uncovered.scripting.providers.openai_live import OpenAIModel
from tech_uncovered.scripting.token_count import count_tokens
from tests.script_helpers import config


class RankingTests(unittest.TestCase):
    def setUp(self):
        self.cfg=config();self.subjects=['Example Model 7']
        self.product='https://developers.openai.com/api/docs/models/example-model-7'
        self.launch='https://openai.com/index/example-model-7/'
        self.academy='https://academy.openai.com/en/pages/general-resources'
        self.pdf='https://cdn.openai.com/pdf/GPT-as-a-measurement-tool.pdf'
    def rank(self,category='IDENTITY_EVENT'):
        return rank_results([{'url':u} for u in [self.academy,self.pdf,self.product,self.launch]],{'category':category},self.subjects,self.cfg)
    def test_exact_launch_and_model_outrank_academy_pdf(self):
        r=self.rank();self.assertEqual(r[0]['url'],self.launch);self.assertEqual(r[1]['url'],self.product)
        self.assertEqual(next(x for x in r if x['url']==self.pdf)['selection_rejection'],'REQUIREMENT_MISMATCH')
    def test_requirement_changes_document_priority(self):
        self.assertEqual(self.rank('PRIMARY_DOCUMENTATION')[0]['url'],self.product)
    def test_community_is_not_documentation(self):
        meta=classify('https://community.openai.com/t/example',self.cfg['resolution_authorities'])
        self.assertEqual(meta['authority_type'],'COMMUNITY');self.assertEqual(meta['source_owner'],'OpenAI Community')
    def test_subdomains_share_owner(self):
        for host in ('openai.com','developers.openai.com','academy.openai.com'):
            self.assertEqual(classify('https://'+host)['source_owner'],'OpenAI')
        self.assertEqual(classify('https://cdn.openai.com/file.pdf')['authority_type'],'HOSTED_DOCUMENT')
        self.assertEqual(classify('https://openai.com.evil.test')['authority_type'],'UNKNOWN')
    def test_canonical_and_localized_duplicates(self):
        urls=[self.launch,self.launch+'?utm_source=x',self.launch+'?video=1',self.launch.rstrip('/'),
              self.launch.replace('/index/','/ka-GE/index/'),self.launch.replace('/index/','/zh-Hans-CN/index/')]
        r=rank_results([{'url':u} for u in urls],{'category':'IDENTITY_EVENT'},self.subjects,self.cfg)
        self.assertEqual(len({group_url(u) for u in urls}),1)
        self.assertEqual(sum(not x['selection_rejection'] for x in r),1)
    def test_url_content_identity_mismatch(self):
        u='https://academy.openai.com/en/pages/example-model-5-launch-resources'
        r=score_result({'url':u},{'category':'IDENTITY_EVENT'},self.subjects,self.cfg,
                       source={'title':'Example Model 5 resources','headings':['Example Model 7 launch resources'],'text':'Example Model 7'})
        self.assertIn('CONTENT_URL_MISMATCH',r['selection_warnings']);self.assertFalse(r['eligible_for_primary_identity'])
    def test_deterministic_components_and_order(self):
        hits=[{'url':self.product},{'url':self.launch}]
        a=rank_results(hits,{'category':'PRIMARY_DOCUMENTATION'},self.subjects,self.cfg)
        b=rank_results(list(reversed(hits)),{'category':'PRIMARY_DOCUMENTATION'},self.subjects,self.cfg)
        self.assertEqual(a,b)
        self.assertAlmostEqual(a[0]['selection_score'],sum(self.cfg['source_selection_weights'][k]*v for k,v in a[0]['selection_components'].items()))
    def test_unknown_freshness_is_zero(self):
        self.assertEqual(self.rank()[0]['freshness_hint'],0)
    def test_post_fetch_community_stays_community(self):
        r=score_result({'url':'https://community.openai.com/t/example-model-7'}, {'category':'PRIMARY_DOCUMENTATION'},self.subjects,self.cfg,
            source={'title':'Example Model 7','text':'Example Model 7 official documentation'})
        self.assertEqual(r['authority_type'],'COMMUNITY')


class ReservationTests(unittest.TestCase):
    def setUp(self):
        self.cfg=config()
        for target in ('socket.create_connection','socket.getaddrinfo','urllib.request.urlopen'):
            p=patch(target,side_effect=AssertionError('Network forbidden'));p.start();self.addCleanup(p.stop)
    def success(self):
        return {'status':'completed','usage':{'input_tokens':100,'output_tokens':10},
            'output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]}
    def test_actual_local_token_count(self):
        self.assertEqual(count_tokens('hello world',self.cfg),2)
        self.assertEqual(count_tokens('',self.cfg),0)
        self.assertGreater(count_tokens('こんにちは 🌍 café',self.cfg),0)
    def test_reserved_before_dispatch_and_reconciled(self):
        budget=Budget(self.cfg)
        def transport(payload):
            self.assertGreater(budget.reserved,0);self.assertEqual(budget.record.attempts[-1]['status'],'RESERVED')
            self.assertGreater(budget.record.attempts[-1]['input_tokens_local'],0)
            return self.success()
        OpenAIModel('unused',self.cfg,budget,transport).request('test','hello',{})
        r=budget.record;a=r.attempts[0]
        self.assertEqual(r.active_reservation_usd,0)
        self.assertAlmostEqual(a['reserved_cost_usd'],a['actual_cost_usd']+a['released_reserve_usd'])
        self.assertAlmostEqual(r.estimated_cost_upper_bound_usd,r.known_cost_usd)
    def test_failed_reservation_retained_then_retry_success(self):
        budget=Budget(self.cfg);calls=[]
        def transport(payload):
            calls.append(payload)
            if len(calls)==1:raise TimeoutError()
            return self.success()
        OpenAIModel('unused',self.cfg,budget,transport).request('test','hello',{})
        r=budget.record
        self.assertEqual(len(calls),2);self.assertFalse(r.usage_complete)
        self.assertTrue(r.attempts[0]['retry_allowed'])
        self.assertAlmostEqual(r.conservative_unknown_cost_usd,r.attempts[0]['reserved_cost_usd'])
        self.assertAlmostEqual(r.estimated_cost_upper_bound_usd,r.known_cost_usd+r.conservative_unknown_cost_usd)
    def test_no_retry_without_another_full_reservation(self):
        cfg=dict(self.cfg,max_model_cost_usd=.09);b=Budget(cfg);calls=[]
        def fail(p):calls.append(p);raise TimeoutError()
        with self.assertRaises(ProviderFailure):OpenAIModel('unused',cfg,b,fail).request('test','hello',{})
        self.assertEqual(len(calls),1);self.assertFalse(b.record.attempts[0]['retry_allowed'])
        self.assertLessEqual(b.record.estimated_cost_upper_bound_usd,.09)
    def test_no_more_than_one_retry(self):
        b=Budget(self.cfg);calls=[]
        def fail(p):calls.append(p);raise TimeoutError()
        with self.assertRaises(ProviderFailure):OpenAIModel('unused',self.cfg,b,fail).request('test','hello',{})
        self.assertEqual(len(calls),2)
    def test_later_calls_after_unknown_are_budgeted(self):
        b=Budget(self.cfg);r=b.reserve(100);b.unknown('test',r)
        another=b.reserve(100);self.assertGreater(b.record.estimated_cost_upper_bound_usd,r)
        b.settle(another,self.success(),'next')
        self.assertGreater(b.record.estimated_cost_upper_bound_usd,b.record.known_cost_usd)
    def test_numeric_bound_never_reserves_over_dollar(self):
        b=Budget(self.cfg)
        while True:
            try:r=b.reserve(1000)
            except LimitReached:break
            b.unknown('simulated',r)
            self.assertLessEqual(b.record.estimated_cost_upper_bound_usd,1.)
        self.assertTrue(b.record.estimated_cost_upper_bound_usd>0)
    def test_missing_usage_retains_reservation(self):
        b=Budget(self.cfg);r=b.reserve(100)
        self.assertFalse(b.settle(r,{},'test'))
        self.assertEqual(b.record.estimated_cost_upper_bound_usd,r)
    def test_retry_disallowed_if_unsafe_or_out_of_time(self):
        b=Budget(self.cfg)
        self.assertFalse(b.retry_decision(.1,safe=False,attempt=0,max_attempts=2)[0])
        b.started-=301
        self.assertFalse(b.retry_decision(.1,safe=True,attempt=0,max_attempts=2)[0])
    def test_full_rate_used_even_with_cached_pricing(self):
        b=Budget(self.cfg);r=b.reserve(1000)
        self.assertAlmostEqual(r,(1000+1024)*2/1e6+5000*12/1e6)
