import io
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError

from tech_uncovered.database import Database
from tech_uncovered.settings import Settings
from tech_uncovered.youtube import BudgetExceeded, YouTubeClient, YouTubeError, duration_seconds
from tests.test_scoring import NOW


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name)/'test.sqlite3')
        self.calls = []

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def client(self, transport=None, **kwargs):
        def fake(endpoint, params, key):
            self.calls.append((endpoint,params))
            return {'items': []}
        return YouTubeClient('secret', self.db, Settings(), transport=transport or fake,
                             clock=lambda: NOW, sleep=lambda _:None, **kwargs)

    def test_cache_zero_extra_requests_and_no_secret(self):
        client = self.client()
        first = client.get('videos', {'id':'a'}, timedelta(hours=6))
        second = client.get('videos', {'id':'a'}, timedelta(hours=6))
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls),1)
        self.assertEqual(client.usage.to_dict()['cache_hit_rate'],.5)
        self.assertNotIn('secret', str(list(self.db.connection.execute('SELECT * FROM api_cache'))))

    def test_cache_expiry_and_refresh(self):
        client=self.client()
        client.get('videos', {'id':'a'},timedelta(hours=6))
        client.clock=lambda:NOW+timedelta(hours=6)
        client.get('videos', {'id':'a'},timedelta(hours=6))
        self.client(refresh=True).get('videos', {'id':'a'},timedelta(hours=6))
        self.assertEqual(len(self.calls),3)

    def test_budget(self):
        client=self.client()
        client.settings=Settings(request_budget=1)
        client.get('videos', {'id':'a'},timedelta(hours=6))
        with self.assertRaises(BudgetExceeded):
            client.get('videos', {'id':'b'},timedelta(hours=6))
        self.assertEqual(client.usage.requests,1)

    def test_quota_failure_no_retry_no_cache(self):
        def fail(*_):
            raise HTTPError('url-secret',403,'forbidden',{},io.BytesIO(json.dumps({'error':{'errors':[{'reason':'quotaExceeded'}]}}).encode()))
        client=self.client(fail)
        with self.assertRaisesRegex(BudgetExceeded,'quota exhausted'):
            client.get('videos',{},timedelta(hours=6))
        self.assertEqual(client.usage.requests,1)
        self.assertEqual(self.db.connection.execute('SELECT count(*) FROM api_cache').fetchone()[0],0)

    def test_transient_retries_redact_url(self):
        def fail(*_):
            raise URLError('url-with-secret')
        client=self.client(fail)
        with self.assertRaisesRegex(YouTubeError,'after retries') as context:
            client.get('videos',{},timedelta(hours=6))
        self.assertNotIn('secret',str(context.exception))
        self.assertEqual(client.usage.requests,3)

    def test_duration_parser(self):
        for value, expected in [('PT3M',180),('PT1H2M3S',3723),('P1DT1S',86401),('PT0S',0),('bogus',None)]:
            self.assertEqual(duration_seconds(value),expected)

    def test_missing_statistics_preserved(self):
        def fake(*_):
            return {'items':[{'id':'a','snippet':{'channelId':'c','channelTitle':'C','title':'T', 'publishedAt':NOW.isoformat()},'statistics':{'viewCount':'0'},'contentDetails':{'duration':'PT1M'}}]}
        row=self.client(fake).videos(['a'])[0]
        self.assertEqual(row['views'],0)
        self.assertIsNone(row['likes'])
        self.assertIsNone(row['comments'])

    def test_paginated_uploads(self):
        def fake(endpoint, params, key):
            self.calls.append(params)
            if 'pageToken' not in params:
                return {'items':[{'contentDetails':{'videoId':str(i)}} for i in range(50)],'nextPageToken':'next'}
            return {'items':[{'contentDetails':{'videoId':str(i)}} for i in range(50,60)]}
        ids,capped=self.client(fake).uploads({'uploads_playlist_id':'p'})
        self.assertEqual(len(ids),60)
        self.assertFalse(capped)
        self.assertEqual(self.calls[-1]['pageToken'],'next')
