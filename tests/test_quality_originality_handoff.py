import copy
import unittest
from unittest.mock import Mock,patch
from tech_uncovered.scripting.providers.openai_live import ModelScriptQualityReviewer,originality_context

class QualityOriginalityHandoffTests(unittest.TestCase):
    def test_persisted_context_reaches_quality_without_forcing_clear(self):
        selected={'idea':{'idea_id':'i','similarity_status':'CLEAR','originality_notes':'Different objective','similarity_details':{'reference':'neighbor'},'story_context':[{'video_id':'v','competitor_angle':'unknown','flags':['CONTEXT_LIMITED']}]},'competitor_references':[{'video_id':'v','title':'Existing title'}],'trend':{'saturation_uncertain':True}}
        original=copy.deepcopy(selected);model=Mock();model.config={};model.request.return_value={'originality_status':'REVIEW'}
        with patch('tech_uncovered.scripting.providers.openai_live.generation_context',return_value={}),patch('socket.socket.connect',side_effect=AssertionError('No network')):
            result=ModelScriptQualityReviewer(model).review({}, {'pivot_acceptance':True,'safe_angle':'New final angle'},selected)
        payload=model.request.call_args.args[2]
        self.assertEqual(payload['originality_context'],originality_context(selected))
        self.assertEqual(payload['selected']['accepted_angle'],'New final angle')
        self.assertEqual(result['originality_status'],'REVIEW');self.assertEqual(selected,original)
        self.assertIn('never forces CLEAR',model.request.call_args.args[1])
    def test_absent_context_remains_unknown(self):
        context=originality_context({})
        self.assertIsNone(context['original_m2_originality_status'])
        self.assertIsNone(context['similarity_status']);self.assertEqual(context['competitor_references'],[])
        self.assertTrue(context['limitations'])
    def test_normal_flow_preserves_selected_and_result(self):
        model=Mock();model.config={};model.request.return_value={'originality_status':'REJECT'}
        selected={'idea':{'idea_id':'ordinary'}}
        with patch('tech_uncovered.scripting.providers.openai_live.generation_context',return_value={}):
            result=ModelScriptQualityReviewer(model).review({}, {},selected)
        self.assertEqual(model.request.call_args.args[2]['selected'],selected)
        self.assertEqual(result,{'originality_status':'REJECT'})
