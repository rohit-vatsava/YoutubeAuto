import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from tech_uncovered.distribution.adapters import *
from tech_uncovered.distribution.storage import Store
from tech_uncovered.distribution.cli import execute

class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.store=Store(self.root/'m5.db');self.addCleanup(self.store.close)
        self.spec={'video_id':'fixture-video','script_id':'fixture-script','revision':1,'title':'Fixture','creative_dna':{'topic':'fixture','scene_count':9}}
        self.store.save_production(self.spec)
    def test_distribution_never_publishes(self):
        for adapter in (YouTubeDistributionAdapter(),InstagramDistributionAdapter()):
            self.assertFalse(adapter.prepare(self.spec,'local.mp4')['publish_allowed'])
            with self.assertRaises(NotImplementedError):adapter.publish({})
    def test_youtube_units_and_nulls(self):
        row=YouTubeAnalyticsAdapter().normalize('fixture-video',{'views':20,'estimatedMinutesWatched':5},'7d','2026-09-30T00:00:00Z')
        self.assertEqual(row.watch_time,300);self.assertIsNone(row.saves);self.assertIsNone(row.viewed_vs_swiped)
        self.assertEqual(row.source_metric_payload['estimatedMinutesWatched'],5)
    def test_instagram_normalization(self):
        row=InstagramAnalyticsAdapter().normalize('fixture-video',{'views':20,'watch_time_seconds':123,'saved':4},'7d','2026-09-30T00:00:00Z')
        self.assertEqual(row.watch_time,123);self.assertEqual(row.saves,4);self.assertIsNone(row.impressions)
    def test_invalid_metric_rejected(self):
        for value in (-1,True,float('nan'),1.5):
            with self.subTest(value=value),self.assertRaises(ValueError):YouTubeAnalyticsAdapter().normalize('v',{'views':value},'7d','now')
    def test_sqlite_persistence_idempotence_and_conflict(self):
        row=YouTubeAnalyticsAdapter().normalize('fixture-video',{'views':20},'7d','2026-09-30T00:00:00Z')
        self.store.save_performance(row);self.store.save_performance(row)
        self.assertEqual(len(self.store.joined()),1);row.views=30
        with self.assertRaises(ValueError):self.store.save_performance(row)
        with self.assertRaises(sqlite3.IntegrityError):self.store.db.execute("UPDATE performance SET platform='changed'")
    def test_creative_join_platform_and_window(self):
        for cls in (YouTubeAnalyticsAdapter,InstagramAnalyticsAdapter):self.store.save_performance(cls().normalize('fixture-video',{'views':20},'7d','2026-09-30T00:00:00Z'))
        rows=self.store.joined(platform='youtube',window='7d')
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['creative_dna'],self.spec['creative_dna'])
        self.assertEqual(self.store.joined(window='28d'),[])
    def test_preference_history_reversible(self):
        first=self.store.save_preferences({'duration_targets':[50]}, {'source':'fixture'},10)
        second=self.store.save_preferences({'duration_targets':[55]}, {'source':'fixture'},12,first)
        self.assertEqual(self.store.preferences(first),{'duration_targets':[50]});self.assertEqual(self.store.preferences(second),{'duration_targets':[55]})
        with self.assertRaises(sqlite3.IntegrityError):self.store.db.execute('DELETE FROM preferences')
    def test_preference_code_and_small_samples_rejected(self):
        for data,count in (({'python':'print(1)'},10),({'topic_weights':{'AI':'exec'}},10),({'topic_weights':{'AI':1}},9)):
            with self.assertRaises(ValueError):self.store.save_preferences(data,{'source':'test'},count)
    def test_synthetic_two_platform_cli(self):
        spec=self.root/'spec.json';spec.write_text(json.dumps(self.spec));out=self.root/'report.json'
        with patch('socket.socket.connect',side_effect=AssertionError('No live call')),patch('builtins.print'):
            self.assertEqual(execute(SimpleNamespace(spec=spec,fixture=Path('fixtures/distribution/metrics.json'),db=self.root/'integration.db',output=out)),0)
        report=json.loads(out.read_text());self.assertTrue(report['synthetic']);self.assertEqual({r['platform'] for r in report['records']},{'youtube','instagram'})
