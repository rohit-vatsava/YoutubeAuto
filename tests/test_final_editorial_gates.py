import unittest
from tech_uncovered.scripting.pivot_scope import classify,FAILURES
from tech_uncovered.scripting.quality import spoken_diagnostics,normalize_warnings
from tech_uncovered.scripting.readiness import decide

class FinalEditorialGatesTests(unittest.TestCase):
    def test_safe_guidance(self):
        for text in ('Pick the settings you need.','Pick the documented settings and tools you need.','Test them in your environment.','Consider measuring task success.','Compare the result with your requirements.','Verify the behavior before deployment.'):
            with self.subTest(text=text):self.assertEqual(classify(dict(text=text,factual=False),{'topic':'Example','claims':[]})['classification'],'NONFACTUAL_EDITORIAL')
    def test_factual_imperatives_not_exempt(self):
        for text in ('Test it because Astra is faster.','Measure its 2x performance.','Use web search because it is reliable.','Choose Astra because it improves productivity.'):
            with self.subTest(text=text):self.assertIn(classify(dict(text=text,factual=False),{'topic':'Example','claims':[]})['classification'],FAILURES)
    def test_display_excluded_spoken_included(self):
        long=' '.join(['word']*31)
        draft={'sections':[{'name':'BODY','sentences':[{'text':'Short narration.'}]}], 'on_screen_text':[{'text':long}],'visual_notes':[long],'captions':[long],'pronunciation_notes':[long]}
        self.assertEqual(spoken_diagnostics(draft),[])
        draft['sections'][0]['sentences'][0]['text']=long
        self.assertIn('OVERLY_LONG_SENTENCES',spoken_diagnostics(draft))
    def test_hook_and_spoken_cta(self):
        long=' '.join(['word']*31)
        for field,value in [('selected_hook',{'text':long}),('cta',{'text':long,'spoken':True})]:
            self.assertIn('OVERLY_LONG_SENTENCES',spoken_diagnostics({'sections':[],field:value}))
        self.assertEqual(spoken_diagnostics({'sections':[],'cta':{'text':long,'spoken':False}}),[])
    def result(self,quality_status='CLEAR',angle_status='REVIEW',warnings=None,flags=None):
        return decide({'research_status':'SUFFICIENT'},{'word_count':138,'estimated_duration':55.2},{'verdict':'PASS'},
            {'originality_status':quality_status,'score':81,'warnings':warnings or [],'spoken_naturalness':{'flags':flags or []}},
            {'originality_status':angle_status},{'quality_threshold':80,'script_word_min':110,'script_word_max':150,'duration_min_seconds':45,'duration_max_seconds':60})
    def test_final_originality_authority(self):
        self.assertEqual(self.result()['status'],'READY_FOR_PRODUCTION')
        self.assertEqual(self.result('REVIEW')['status'],'READY_FOR_PRODUCTION')
        self.assertEqual(self.result('REJECT')['status'],'REJECTED')
        self.assertEqual(self.result(angle_status='REJECT')['status'],'REJECTED')
    def test_typed_warning_gate(self):
        warning=dict(category='CAUTION',severity='WARNING',blocking=False,text='Keep attribution')
        self.assertEqual(self.result(warnings=[warning])['status'],'READY_FOR_PRODUCTION')
        warning['blocking']=True
        self.assertIn('EDITORIAL_WARNINGS',self.result(warnings=[warning])['reasons'])
    def test_legacy_and_malformed_warnings_conservative(self):
        for warning in ('Production caution',{'text':'Unknown'}, {'text':'Unknown','blocking':'false','severity':'INFO'}):
            self.assertTrue(normalize_warnings([warning])[0]['blocking'])
            self.assertIn('EDITORIAL_WARNINGS',self.result(warnings=[warning])['reasons'])
    def test_naturalness_truth_table(self):
        self.assertNotIn('SPOKEN_NATURALNESS_REVIEW',self.result(flags=[])['reasons'])
        self.assertIn('SPOKEN_NATURALNESS_REVIEW',self.result(flags=[dict(category='READABILITY',severity='ERROR',blocking=True,text='Severe readability failure')])['reasons'])
    def test_originality_review_is_advisory(self):
        r=self.result('REVIEW')
        self.assertEqual(r['status'],'READY_FOR_PRODUCTION')
        self.assertIn('ORIGINALITY_REVIEW',r['advisories'])
    def test_naturalness_explicit_blocking_only(self):
        for finding in ('jargon',dict(category='JARGON',severity='INFO',blocking=False,text='Technical audience')):
            self.assertEqual(self.result(flags=[finding])['status'],'READY_FOR_PRODUCTION')
        self.assertEqual(self.result(flags=[dict(category='UNUSABLE',severity='ERROR',blocking=True,text='Broken narration')])['status'],'EDITORIAL_REVIEW')
    def test_quality_floor_and_factual_deficiency(self):
        packet={'research_status':'SUFFICIENT'};draft={'word_count':138,'estimated_duration':55.2}
        quality={'score':80,'originality_status':'REVIEW','spoken_naturalness':{'flags':[]},'warnings':[]}
        cfg={'quality_threshold':75,'script_word_min':110,'script_word_max':150,'duration_min_seconds':45,'duration_max_seconds':60}
        self.assertEqual(decide(packet,draft,{'verdict':'PASS'},quality,{},cfg)['status'],'READY_FOR_PRODUCTION')
        quality['score']=74;cfg['quality_threshold']=70
        self.assertEqual(decide(packet,draft,{'verdict':'PASS'},quality,{},cfg)['status'],'EDITORIAL_REVIEW')
        self.assertEqual(decide(packet,draft,{'verdict':'RESEARCH_REQUIRED'},quality,{},cfg)['status'],'RESEARCH_REQUIRED')
        self.assertEqual(decide(packet,draft,{'verdict':'PASS'},None,{},cfg)['status'],'EDITORIAL_REVIEW')
