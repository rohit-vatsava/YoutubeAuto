import contextlib
import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from tech_uncovered.cli import main
from tech_uncovered.database import Database
from tech_uncovered.reports import export
from tech_uncovered.research import analyze, collect
from tech_uncovered.settings import Settings
from tech_uncovered.topics import DictionaryTopicClassifier
from tech_uncovered.youtube import Usage, YouTubeClient, YouTubeError
from tests.test_scoring import NOW, video

ROOT=Path(__file__).resolve().parent.parent


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)
        self.db=Database(self.path/'test.sqlite3')

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def result(self, rows):
        return analyze(rows,[],Settings(),DictionaryTopicClassifier({}),NOW,'synthetic',Usage().to_dict())

    def test_persist_all_score_fields_and_null(self):
        result=self.result([video(i) for i in range(9)])
        self.db.save_videos(result['videos'])
        self.db.save_run(result)
        row=dict(self.db.connection.execute('SELECT * FROM video_scores LIMIT 1').fetchone())
        self.assertIsNone(row['outlier_ratio'])
        self.assertIsNone(row['velocity_ratio'])
        self.assertIsNone(row['velocity_adjusted_score'])
        self.assertIsNone(row['percentile'])
        self.assertEqual(row['baseline_sample_size'],9)
        self.assertEqual(row['baseline_median_views'],100000)
        self.assertEqual(row['eligibility_reason'],'insufficient_baseline_sample')

    def test_reports_empty_and_csv_formula_escape(self):
        result=self.result([video(1,title='=HYPERLINK("bad")')])
        export(result,self.path/'reports')
        self.assertIn("'=HYPERLINK",(self.path/'reports/outliers.csv').read_text())
        loaded=json.loads((self.path/'reports/outliers.json').read_text())
        self.assertEqual(loaded['videos'][0]['title'],'=HYPERLINK("bad")')
        self.assertIn('Insufficient evidence',(self.path/'reports/top_topics.md').read_text())
        self.assertFalse(list((self.path/'reports').glob('.radar-*')))

    def test_synthetic_cli_has_no_network(self):
        with patch('tech_uncovered.youtube.urlopen',side_effect=AssertionError('Network prohibited')),contextlib.redirect_stdout(io.StringIO()) as output:
            code=main(['research','--fixture',str(ROOT/'tests/fixtures/synthetic.json'),
                       '--db',str(self.path/'demo.sqlite3'),'--reports-dir',str(self.path/'demo')])
        self.assertEqual(code,0)
        self.assertIn('Quota units estimated used: 0',output.getvalue())
        result=json.loads((self.path/'demo/outliers.json').read_text())
        self.assertEqual(len(result['videos']),26)
        self.assertEqual(len(result['outliers']),4)
        self.assertEqual(sum(r['provisional'] for r in result['videos']),2)
        self.assertEqual(result['schema_version'],'1.0')

    def test_live_boundary_collection_and_warm_cache(self):
        calls=[]
        def fake(endpoint,params,key):
            calls.append(endpoint)
            if endpoint=='channels':
                return {'items':[{'id':'one','snippet':{'title':'One'},'contentDetails':{'relatedPlaylists':{'uploads':'p'}}}]}
            if endpoint=='playlistItems':
                return {'items':[{'contentDetails':{'videoId':str(i)}} for i in range(12)]}
            return {'items':[{'id':str(i),'snippet':{'channelId':'one','channelTitle':'One','title':'GPT model release',
                              'publishedAt':(NOW-timedelta(days=20)).isoformat()},
                              'contentDetails':{'duration':'PT2M'},'statistics':{'viewCount':str(1000 if i<10 else 10000)}} for i in range(12)]}
        def run():
            client=YouTubeClient('secret',self.db,Settings(),transport=fake,clock=lambda:NOW)
            rows,channels,failures,warnings=collect(client,self.db,[{'name':'One','handle':'@one'}])
            return rows,channels,failures,client
        rows,channels,failures,client=run()
        self.assertEqual(len(rows),12)
        self.assertEqual(failures,[])
        self.assertEqual(client.usage.requests,3)
        rows,channels,failures,client=run()
        self.assertEqual(len(calls),3)
        self.assertEqual(client.usage.requests,0)
        self.assertEqual(client.usage.to_dict()['cache_hit_rate'],1)

    def test_partial_channel_failure_continues(self):
        class Fake:
            settings=Settings()
            def resolve_channel(self, config):
                if config['name']=='Bad':raise YouTubeError('Not found')
                return dict(channel_id='one',name='Good',handle='@good',uploads_playlist_id='p',observed_at=NOW.isoformat())
            def uploads(self,channel): return ['1'],False
            def videos(self,ids): return [video('1')]
        rows,channels,failures,warnings=collect(Fake(),self.db,[{'name':'Bad'},{'name':'Good'}])
        self.assertEqual(len(rows),1)
        self.assertEqual(len(channels),1)
        self.assertEqual(len(failures),1)

    def test_unavailable_existing_video_invalidated(self):
        self.db.save_videos([video('1')])
        class Fake:
            settings=Settings()
            def resolve_channel(self,config):return dict(channel_id='one',name='One',handle='@one',uploads_playlist_id='p',observed_at=NOW.isoformat())
            def uploads(self,channel):return ['1'],False
            def videos(self,ids):return []
        rows,_,_,warnings=collect(Fake(),self.db,[{'name':'One'}])
        self.assertFalse(rows[0]['available'])
        self.assertIsNone(rows[0]['views'])
        self.assertTrue(warnings)

    def test_retention_preserves_radar_history(self):
        result=self.result([video(1)])
        self.db.save_videos(result['videos'])
        self.db.save_run(result)
        self.db.prune(NOW+timedelta(days=31))
        self.assertEqual(len(self.db.load_videos()),1)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM video_scores').fetchone()[0],1)

    def test_offline_cli_no_network_or_credentials(self):
        channel=dict(channel_id='one',name='One',handle='@one',uploads_playlist_id='p',observed_at=NOW.isoformat())
        self.db.save_channel(channel)
        self.db.save_videos([video(i) for i in range(10)])
        config=self.path/'channels.json'
        config.write_text(json.dumps([{'name':'One','handle':'@one'}]))
        with patch('tech_uncovered.cli.utcnow',return_value=NOW), patch('tech_uncovered.youtube.urlopen',side_effect=AssertionError('Network prohibited')), contextlib.redirect_stdout(io.StringIO()):
            code=main(['research','--offline','--db',str(self.path/'test.sqlite3'),
                       '--channels',str(config),'--reports-dir',str(self.path/'offline')])
        self.assertEqual(code,0)
        result=json.loads((self.path/'offline/outliers.json').read_text())
        self.assertEqual(result['metadata']['mode'],'offline')
        self.assertEqual(result['metadata']['usage']['requests'],0)
        self.assertEqual(len(result['videos']),10)

    def test_historical_run_preserved_without_rewriting_observation(self):
        result=self.result([video(1)])
        result['generated_at']=(NOW+timedelta(days=29)).isoformat()
        self.db.save_run(result)
        self.db.prune(NOW+timedelta(days=31))
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM research_runs').fetchone()[0],1)

    def test_positive_score_fields_persist(self):
        result=self.result([video(i) for i in range(10)]+[video('hot',views=400000)])
        self.db.save_run(result)
        row=dict(self.db.connection.execute("SELECT * FROM video_scores WHERE video_id='hot'").fetchone())
        self.assertEqual(row['outlier_ratio'],4)
        self.assertEqual(row['velocity_ratio'],4)
        self.assertEqual(row['velocity_adjusted_score'],4)
        self.assertGreater(row['percentile'],90)
        self.assertEqual(row['baseline_sample_size'],11)
        self.assertEqual(row['baseline_median_views_per_day'],5000)
        self.assertEqual(row['eligibility_reason'],'eligible')
