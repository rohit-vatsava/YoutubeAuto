import unittest
from unittest.mock import patch
from tech_uncovered.scripting.costs import Budget,LimitReached,ProviderFailure
from tech_uncovered.scripting.providers.openai_live import OpenAIModel
from tests.script_helpers import config


class AdapterTests(unittest.TestCase):
    def test_configurable_model_and_strict_schema_without_network(self):
        cfg=config();cfg['model_name']='configured-test-model';cfg['pricing']['model_name']=cfg['model_name'];budget=Budget(cfg);payloads=[]
        def transport(payload):
            payloads.append(payload)
            return {'id':'fake','status':'completed','usage':{'input_tokens':100,'output_tokens':10},'output':[{'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}]}
        self.assertEqual(OpenAIModel('not-a-key',cfg,budget,transport).request('check','Test',{}, {'ok':False}),{'ok':True})
        self.assertEqual(payloads[0]['model'],'configured-test-model');self.assertTrue(payloads[0]['text']['format']['strict'])
        self.assertNotIn('not-a-key',str(payloads));self.assertAlmostEqual(budget.record.estimated_model_cost_usd,.00032)
    def test_cost_limit_prevents_dispatch(self):
        cfg=config();cfg['max_model_cost_usd']=.000001;budget=Budget(cfg)
        with patch.object(OpenAIModel,'_http') as http:
            with self.assertRaises(LimitReached):OpenAIModel('x',cfg,budget).request('x','x',{}, {'x':False})
            http.assert_not_called()
    def test_unknown_pricing_prevents_dispatch(self):
        cfg=config();cfg['model_name']='unknown';budget=Budget(cfg)
        with self.assertRaises(LimitReached):budget.reserve(100)
    def test_transport_uncertainty_retained_but_future_calls_budgeted(self):
        cfg=config();budget=Budget(cfg);calls=[]
        def fail(payload):calls.append(payload);raise TimeoutError()
        model=OpenAIModel('x',cfg,budget,fail)
        with self.assertRaises(ProviderFailure):model.request('x','x',{})
        with self.assertRaises(ProviderFailure):model.request('x','x',{})
        self.assertEqual(len(calls),4)
        self.assertGreater(budget.record.conservative_unknown_cost_usd,0)
        self.assertLessEqual(budget.record.estimated_cost_upper_bound_usd,cfg['max_model_cost_usd'])
        self.assertFalse(budget.record.usage_complete)
    def test_missing_usage_not_reported_as_free(self):
        cfg=config();budget=Budget(cfg);model=OpenAIModel('x',cfg,budget,lambda p:{'output':[]})
        with self.assertRaises(ProviderFailure):model.request('x','x',{})
        self.assertFalse(budget.record.usage_complete)
    def test_refusal_fails_safely(self):
        cfg=config();budget=Budget(cfg);model=OpenAIModel('x',cfg,budget,lambda p:{'usage':{'input_tokens':1,'output_tokens':1},'output':[]})
        with self.assertRaises(ProviderFailure):model.request('x','x',{})
    def test_actual_search_tool_cost_is_separate(self):
        cfg=config();budget=Budget(cfg);r=budget.reserve(100,search=True)
        budget.settle(r,{'usage':{'input_tokens':100,'output_tokens':100},'output':[{'type':'web_search_call'}]},'search')
        self.assertEqual(budget.record.estimated_search_cost_usd,.01)
