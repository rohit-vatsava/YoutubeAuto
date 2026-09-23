import unittest
from copy import deepcopy
from datetime import timedelta
from tech_uncovered.intelligence.models import StoryBrief
from tech_uncovered.intelligence.generation import DeterministicIdeaGenerator
from tech_uncovered.intelligence.scoring import COMPONENTS,apply_readiness,score_idea,validate_config,weighted_score
from tests.intelligence_helpers import config,NOW


class IntelligenceScoringTests(unittest.TestCase):
    def setUp(self):
        self.brief=StoryBrief(video_id='v',canonical_subject='AI model',core_event='Fictional release',
                              evergreen_or_news='news',event_date='2026-09-19',context_summary='An announcement',
                              factual_claims=[{'claim_id':'c','text':'Fictional claim','material':True,'status':'VERIFIED','evidence_ids':['e'],'supports_event_date':'2026-09-19'}])
        self.cluster={'cluster_id':'t','canonical_topic':'AI model','median_outlier_score':4,
                      'number_of_distinct_channels':2,'recency':{'median_age_days':1},'saturation_score':0}
        self.candidate={'video_id':'v','published_at':'2026-09-19T00:00:00+00:00'}
        self.idea=DeterministicIdeaGenerator().generate(self.brief,self.cluster)[0]
        self.idea.similarity_details={'similarity':10}
        self.idea.similarity_status='CLEAR'

    def score(self,**kwargs):
        return score_idea(self.idea,self.cluster,[self.brief],[self.candidate],kwargs.get('config',config()),kwargs.get('now',NOW))

    def test_exact_formula(self):
        values={name:80 for name in COMPONENTS}
        self.assertAlmostEqual(weighted_score(values,config()['weights']),77)

    def test_configurable_weights(self):
        cfg=config();cfg['weights']={k:float(k=='EvidenceQuality') for k in COMPONENTS}
        validate_config(cfg)
        self.assertEqual(self.score(config=cfg).idea_score,100)

    def test_invalid_weights(self):
        cfg=config();cfg['weights']['Freshness']=2
        with self.assertRaises(ValueError):validate_config(cfg)

    def test_stale_penalty(self):
        fresh=self.score().scores['Freshness']
        old=self.score(now=NOW+timedelta(days=60))
        self.assertLess(old.scores['Freshness'],fresh)
        self.assertIn('STALE_NEWS',old.risk_flags)

    def test_low_evidence_gate(self):
        self.brief.uncertain_claims=self.brief.factual_claims;self.brief.factual_claims=[]
        self.brief.uncertain_claims[0]['status']='UNVERIFIED'
        idea=self.score()
        self.assertEqual(idea.scores['EvidenceQuality'],0)
        self.assertIn('RESEARCH_REQUIRED',idea.risk_flags)
        self.assertFalse(idea.production_ready)

    def test_high_score_is_not_readiness(self):
        idea=self.score()
        self.assertGreater(idea.idea_score,65)
        self.assertEqual(idea.scores['EvidenceQuality'],100)
        self.assertFalse(idea.production_ready)
        self.assertTrue(idea.required_research)

    def test_all_explicit_gates_allow_readiness_independent_of_score(self):
        idea=self.score();idea.required_research=[];idea.risk_flags=[];idea.idea_score=1
        apply_readiness(idea,config())
        self.assertTrue(idea.production_ready)
        self.assertEqual(idea.category,'READY FOR SCRIPTING')

    def test_each_readiness_blocker(self):
        idea=self.score();idea.required_research=[];idea.risk_flags=[]
        for flag in ['FACTUAL_REVIEW_REQUIRED','EDITORIAL_REVIEW_REQUIRED','CONTEXT_LIMITED','REJECT_NEAR_DUPLICATE','PROVIDER_FAILURE']:
            idea.risk_flags=[flag];apply_readiness(idea,config());self.assertFalse(idea.production_ready)
        idea.risk_flags=[];idea.similarity_status='REVIEW';apply_readiness(idea,config());self.assertFalse(idea.production_ready)
        idea.similarity_status='CLEAR';idea.scores['EvidenceQuality']=59;apply_readiness(idea,config());self.assertFalse(idea.production_ready)

    def test_originality_rejection(self):
        self.idea.similarity_status='REJECT';self.idea.similarity_details={'similarity':95}
        idea=self.score()
        self.assertIn('REJECT_NEAR_DUPLICATE',idea.risk_flags)
        self.assertEqual(idea.category,'REJECTED / REVIEW REQUIRED')

    def test_multi_channel_demand(self):
        two=self.score().scores['DemandSignal']
        self.cluster['number_of_distinct_channels']=1
        self.assertLess(self.score().scores['DemandSignal'],two)

    def test_unverified_event_date_uses_capped_proxy(self):
        self.brief.factual_claims[0].pop('supports_event_date')
        idea=self.score()
        self.assertLessEqual(idea.scores['Freshness'],60)
        self.assertEqual(idea.score_rationale['freshness_date_bases'],['publication_date_proxy'])
