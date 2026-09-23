import unittest
from copy import deepcopy
from datetime import timedelta
from tech_uncovered.intelligence.clustering import cluster_stories
from tech_uncovered.intelligence.models import StoryBrief
from tests.intelligence_helpers import load,config,NOW


class ClusteringTests(unittest.TestCase):
    def items(self):
        videos=[v for v in load('radar.json')['videos'] if v['video_id'].endswith('-10')]
        briefs=[StoryBrief(video_id=v['video_id'],canonical_subject='Orbit compiler',core_event='Release',
                           event_key='Orbit 2 release',evergreen_or_news='news',competitor_angle='demonstration') for v in videos]
        return briefs,videos

    def test_multi_video_multi_channel(self):
        briefs,videos=self.items()
        clusters=cluster_stories(briefs,videos,config(),NOW)
        self.assertEqual(len(clusters),1)
        self.assertEqual(clusters[0]['number_of_distinct_channels'],3)
        self.assertEqual(clusters[0]['repeated_angles'],['demonstration'])

    def test_different_version_stays_separate(self):
        briefs,videos=self.items()
        briefs[-1].event_key='Orbit 3 release'
        self.assertEqual(len(cluster_stories(briefs,videos,config(),NOW)),2)

    def test_window_does_not_chain_merge(self):
        briefs,videos=self.items()
        for v,age in zip(videos,[0,10,20]):v['published_at']=(NOW-timedelta(days=age)).isoformat()
        self.assertEqual(len(cluster_stories(briefs,videos,config(),NOW)),2)

    def test_context_limited_never_merges_on_broad_label(self):
        briefs,videos=self.items()
        for b in briefs:b.flags=['CONTEXT_LIMITED']
        self.assertEqual(len(cluster_stories(briefs,videos,config(),NOW)),3)

    def test_channel_breadth_preference(self):
        briefs,videos=self.items()
        briefs[-1].event_key='Different'
        videos[-1]['velocity_adjusted_score']=10000
        clusters=cluster_stories(briefs,videos,config(),NOW)
        self.assertEqual(clusters[0]['number_of_distinct_channels'],2)

    def test_unknown_identity_singletons(self):
        briefs,videos=self.items()
        for b in briefs:b.event_key=None
        self.assertEqual(len(cluster_stories(briefs,videos,config(),NOW)),3)
