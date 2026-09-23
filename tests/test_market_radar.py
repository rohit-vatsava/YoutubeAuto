import copy
import json
import unittest
from pathlib import Path
from tech_uncovered.market import hints,enrich,normalize,balanced_median
from tech_uncovered.research import analyze
from tech_uncovered.scoring import score_videos
from tech_uncovered.settings import Settings
from tech_uncovered.youtube import Usage
from tech_uncovered.topics import DictionaryTopicClassifier
from tests.test_scoring import NOW,video
ROOT=Path(__file__).resolve().parents[1]


def data():
    cohorts=json.loads((ROOT/'config/cohorts.json').read_text());rules=json.loads((ROOT/'config/radar_rules.json').read_text())
    config={'competitor_config_version':'test-1','channels':[]};videos=[];channels=[]
    for i,cohort in enumerate(('AI_FRONTIER','HARDWARE_CHIPS','TECH_BUSINESS')):
        cid=str(i);config['channels'].append(dict(channel_id=cid,cohort=cohort,enabled=True,weight=1.,source_role='vendor_official' if i==1 else 'independent_creator'))
        channels.append(dict(channel_id=cid,name=cid,window_days=90))
        for n in range(12):videos.append(video(cid+'-'+str(n),channel_id=cid,title='NVIDIA Blackwell architecture announced' if n==11 else 'Routine coverage',views=1000000 if n==11 else 100000))
    result=analyze(videos,channels,Settings(),DictionaryTopicClassifier({}),NOW,'synthetic',Usage().to_dict())
    return result,config,cohorts,rules

class MarketTests(unittest.TestCase):
    def test_original_scores_unchanged(self):
        result,c,cohorts,rules=data();before={r['video_id']:{k:r[k] for k in ('outlier_ratio','velocity_ratio','velocity_adjusted_score','percentile','rank')} for r in result['videos']}
        enrich(result,c,cohorts,rules)
        self.assertEqual(before,{r['video_id']:{k:r[k] for k in ('outlier_ratio','velocity_ratio','velocity_adjusted_score','percentile','rank')} for r in result['videos']})
    def test_cohort_and_cross_cohort_counts(self):
        result=enrich(*data());s=result['cross_cohort_signals'][0]
        self.assertEqual(s['distinct_channel_count'],3);self.assertEqual(s['distinct_cohort_count'],3)
        self.assertEqual(s['independent_channel_count'],2);self.assertEqual(s['vendor_channel_count'],1)
        self.assertEqual(result['cohort_summaries'][0]['qualifying_outliers'],1)
    def test_vendor_role_does_not_change_score(self):
        d=data();a=enrich(*copy.deepcopy(d));d[1]['channels'][1]['source_role']='independent_creator';b=enrich(*d)
        self.assertEqual([r['opportunity_score'] for r in a['opportunities']],[r['opportunity_score'] for r in b['opportunities']])
    def test_channel_balanced_median(self):
        rows=[{'channel_id':'a','score':1}]*100+[{'channel_id':'b','score':9}]
        self.assertEqual(balanced_median(rows,'score',{'a':{'weight':1},'b':{'weight':1}}),5)
    def test_hype_penalty(self):
        rules=data()[3];v=hints('This new AI changes everything',rules);named=hints('NVIDIA RTX 5090 architecture announced',rules)
        self.assertEqual(v['researchability_score'],0);self.assertGreaterEqual(named['researchability_score'],80)
    def test_cve_extraction(self):
        h=hints('CVE-2026-12345 vulnerability explained',data()[3]);self.assertIn('CVE-2026-12345',h['named_entity_hints']);self.assertGreaterEqual(h['researchability_score'],60)
    def test_production_rules(self):
        rules=data()[3]
        self.assertEqual(hints('NVIDIA RTX 5090 benchmark review',rules)['production_fit'],'POOR')
        self.assertEqual(hints('NVIDIA Blackwell architecture',rules)['production_fit'],'GOOD')
        self.assertEqual(hints('My thoughts about stuff',rules)['production_fit'],'MEDIUM')
    def test_opportunity_formula(self):
        r=enrich(*data())['opportunities'][0]
        self.assertAlmostEqual(r['opportunity_score'],.55*r['normalized_radar_signal']+.25*r['researchability_score']+.20*r['cross_cohort_support'])
        self.assertEqual(normalize(8),100)
    def test_version_provenance(self):
        r=enrich(*data());self.assertEqual(r['competitor_config_version'],'test-1');self.assertEqual(r['scoring_version'],'1.0');self.assertIn('configuration_hash',r['metadata']['market_config'])
    def test_deterministic(self):
        d=data();self.assertEqual(enrich(*copy.deepcopy(d)),enrich(*copy.deepcopy(d)))
    def test_old_videos_not_current_opportunities(self):
        d=data()
        for r in d[0]['videos']:r['published_at']='2025-01-01T00:00:00+00:00'
        self.assertEqual(enrich(*d)['opportunities'],[])
    def test_provisional_null_opportunity(self):
        d=data();d[0]['videos'][0]['eligibility_reason']='under_24_hours';d[0]['videos'][0]['provisional']=True
        r=enrich(*d)['videos'][0];self.assertIsNone(r['opportunity_score'])
    def test_cross_signal_components(self):
        s=enrich(*data())['cross_cohort_signals'][0];p=s['components']
        self.assertAlmostEqual(s['signal_strength'],100*(.45*p['cohort_breadth']+.20*p['channel_breadth']+.25*p['radar']+.10*p['recency']))
    def test_same_channel_repetition_not_breadth(self):
        d=data()
        for c in d[1]['channels']:c['cohort']='AI_FRONTIER'
        self.assertEqual(enrich(*d)['cross_cohort_signals'],[])
    def test_phone_review_and_impressions_are_harder(self):
        rules=data()[3]
        self.assertEqual(hints("iPhone 18 Pro Max Review - Apple's Hyping The Wrong Thing",rules)['production_fit'],'POOR')
        self.assertEqual(hints('iPhone Duo Impressions - They NAILED This',rules)['production_fit'],'POOR')
    def test_software_review_not_assumed_physical(self):
        self.assertNotEqual(hints('Claude review',data()[3])['production_fit'],'POOR')
    def test_hardware_comparison_test_metadata(self):
        self.assertEqual(hints('Is the Radeon actually faster than GeForce?',data()[3])['production_fit'],'POOR')
    def test_channel_specific_window(self):
        from datetime import timedelta
        videos=[video(str(i),channel_id='low',published_at=(NOW-timedelta(days=120)).isoformat()) for i in range(11)]
        videos+=[video('h'+str(i),channel_id='high',published_at=(NOW-timedelta(days=120)).isoformat()) for i in range(11)]
        channels=[dict(channel_id='low',name='low',window_days=180),dict(channel_id='high',name='high',window_days=90)]
        result=analyze(videos,channels,Settings(),DictionaryTopicClassifier({}),NOW,'synthetic',Usage().to_dict())
        self.assertTrue(all(r['eligibility_reason']=='eligible' for r in result['videos'] if r['channel_id']=='low'))
        self.assertTrue(all(r['eligibility_reason']=='outside_lookback' for r in result['videos'] if r['channel_id']=='high'))
