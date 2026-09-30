import json
import tempfile
import unittest
from pathlib import Path
from tech_uncovered.production.agnes import AgnesVideoProvider, AgnesVideoRequest, AgnesError, FREE_MODEL
from tech_uncovered.production.assets import AssetRouter


class AgnesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)
        self.calls = []

    def provider(self, responses, **kwargs):
        def transport(method, url, payload, key):
            self.calls.append((method, url, payload))
            value = responses.pop(0)
            if isinstance(value, Exception):
                raise value
            return value, {'x-ratelimit-remaining': '1'}
        return AgnesVideoProvider('test-secret', dry_run=False, free_access_confirmed=True,
                                  transport=transport, sleep=lambda _: None, **kwargs)

    def test_dry_run_no_transport(self):
        p = self.provider([])
        p.dry_run = True
        result = p.generate(AgnesVideoRequest('boat'), self.path)
        self.assertEqual(result['status'], 'DRY_RUN')
        self.assertEqual(self.calls, [])
        self.assertFalse((self.path / 'submission-reserved.json').exists())

    def test_payload_modern_free_only(self):
        p = AgnesVideoRequest('boat').payload()
        self.assertEqual((p['model'], p['mode'], p['seconds'], p['n']), (FREE_MODEL, 'text', '4', 1))
        self.assertNotIn('num_frames', p)

    def test_image_to_video_same_endpoint_no_upload(self):
        p = AgnesVideoRequest('boat', first_frame='https://example.org/boat.png').payload()
        self.assertEqual(p['mode'], 'keyframe')
        self.assertNotIn('image', p)

    def test_bad_parameters(self):
        for req in (AgnesVideoRequest(''), AgnesVideoRequest('a', seconds=3),
                    AgnesVideoRequest('a', seconds=True), AgnesVideoRequest('a', aspect_ratio='auto'),
                    AgnesVideoRequest('a', first_frame='/tmp/a.png')):
            with self.subTest(req=req), self.assertRaises(ValueError):
                req.payload()

    def test_missing_key_blocks(self):
        p = self.provider([])
        p.api_key = ''
        with self.assertRaises(AgnesError):
            p.generate(AgnesVideoRequest('boat'), self.path)
        self.assertFalse(self.calls)

    def test_unconfirmed_free_blocks(self):
        p = self.provider([])
        p.free_access_confirmed = False
        with self.assertRaises(AgnesError):
            p.generate(AgnesVideoRequest('boat'), self.path)
        self.assertFalse(self.calls)

    def test_polling_and_success(self):
        p = self.provider([{'video_id':'v1'}, {'status':'queued'},
                           {'status':'completed', 'url':'https://example.org/test.mp4'}])
        r = p.generate(AgnesVideoRequest('boat'), self.path)
        self.assertEqual([c[0] for c in self.calls], ['POST','GET','GET'])
        self.assertIn('video_id=v1&model_name=', self.calls[-1][1])
        self.assertEqual(r['generation_calls'], 1)
        self.assertIsNone(r['file_size_bytes'])
        self.assertNotIn('test-secret', (self.path/'result.json').read_text())

    def test_error_no_retry_and_reserved(self):
        p = self.provider([AgnesError('HTTP 429')])
        with self.assertRaises(AgnesError):
            p.generate(AgnesVideoRequest('boat'), self.path)
        with self.assertRaises(FileExistsError):
            p.generate(AgnesVideoRequest('boat'), self.path)
        self.assertEqual(len(self.calls), 1)

    def test_no_task_id_fallback(self):
        with self.assertRaises(AgnesError):
            self.provider([{'task_id':'t1'}]).generate(AgnesVideoRequest('boat'), self.path)
        self.assertEqual(len(self.calls), 1)

    def test_failed_task_stops(self):
        with self.assertRaises(AgnesError):
            self.provider([{'video_id':'v1'}, {'status':'failed'}]).generate(AgnesVideoRequest('boat'), self.path)
        self.assertEqual(len(self.calls), 2)

    def test_bounded_polling(self):
        with self.assertRaises(AgnesError):
            self.provider([{'video_id':'v1'}, {'status':'pending'}], max_polls=1).generate(AgnesVideoRequest('boat'), self.path)
        self.assertEqual(len(self.calls), 2)

    def test_unknown_status_stops(self):
        with self.assertRaises(AgnesError):
            self.provider([{'video_id':'v1'}, {'status':'mystery'}]).generate(AgnesVideoRequest('boat'), self.path)

    def test_router_boundary(self):
        p = self.provider([])
        p.dry_run = True
        asset = AssetRouter().generate_video('test', AgnesVideoRequest('boat'), provider=p, output=self.path)
        self.assertEqual(asset.status, 'DRY_RUN')
        self.assertEqual(asset.source_type, 'generated_video')
        self.assertIsNone(asset.path)

    def test_missing_url_stops(self):
        with self.assertRaises(AgnesError):
            self.provider([{'video_id':'v1'}, {'status':'completed'}]).generate(AgnesVideoRequest('boat'), self.path)
