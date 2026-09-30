import io,json,tempfile,unittest,urllib.error,subprocess
from pathlib import Path
from unittest.mock import patch
from tech_uncovered.production.huggingface_video import (
 GeneratedVideoRequest,HuggingFaceVideoProvider,PARAMETERS,ENDPOINT,HOST,
 PublicGradioTransport,VideoProviderError,validate_video)
from tech_uncovered.production.assets import AssetRouter

class Response(io.BytesIO):
 status=200

class Fake:
 def __init__(self,items):self.items=items;self.calls=[]
 def open(self,method,url,payload=None,timeout=30):
  self.calls.append((method,url,payload))
  r=self.items.pop(0)
  if isinstance(r,Exception):raise r
  return Response(r if isinstance(r,bytes) else json.dumps(r).encode())

def schema():return {'named_endpoints':{ENDPOINT:{'parameters':[{'parameter_name':p} for p in PARAMETERS]}}}
def event(kind,data):return ('event: '+kind+'\ndata: '+json.dumps(data)+'\n\n').encode()

class HFVideoTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.ffmpeg=self.root/'ffmpeg';self.ffmpeg.touch()
 def run_provider(self,items,**kwargs):
  self.fake=Fake(items)
  self.provider=HuggingFaceVideoProvider(dry_run=False,ffmpeg=self.ffmpeg,transport=self.fake,
   validator=lambda *a:{'full_decode_passed':True},**kwargs)
  return self.provider.generate(GeneratedVideoRequest('glowing circuits'),self.root/'run')
 def test_dry_run_no_calls(self):
  t=Fake([]);r=HuggingFaceVideoProvider(transport=t).generate(GeneratedVideoRequest('a'),self.root)
  self.assertEqual(r.status,'DRY_RUN');self.assertFalse(t.calls)
 def test_exact_schema(self):
  d=GeneratedVideoRequest('a').data();self.assertEqual(len(d),len(PARAMETERS))
  self.assertEqual(d[4:8],[1024,576,'text-to-video',4]);self.assertEqual(d[-3:],[False,1.0,False])
 def test_invalid_request(self):
  for r in [GeneratedVideoRequest(''),GeneratedVideoRequest('a',seconds=float('nan')),GeneratedVideoRequest('a',width=720)]:
   with self.assertRaises(ValueError):r.data()
 def test_validator_dependency_before_network(self):
  t=Fake([])
  with self.assertRaises(ValueError):HuggingFaceVideoProvider(dry_run=False,transport=t).generate(GeneratedVideoRequest('a'),self.root)
  self.assertFalse(t.calls)
 def test_success_one_each(self):
  r=self.run_provider([schema(),{'event_id':'e1'},event('heartbeat',None)+event('complete',[{'video':{'url':HOST+'/gradio_api/file=test.mp4'}},42]),b'mp4'])
  self.assertEqual(r.status,'VALIDATED_REVIEW_REQUIRED')
  self.assertEqual([c[0] for c in self.fake.calls],['GET','POST','GET','GET'])
  self.assertEqual(r.provenance['download_calls'],1)
 def test_error_fallback_no_download(self):
  r=self.run_provider([schema(),{'event_id':'e1'},event('error','quota exceeded')])
  self.assertEqual(r.status,'LOCAL_MOTION_GRAPHIC');self.assertEqual(r.provenance['download_calls'],0)
  self.assertIn('<animate',Path(r.path).read_text())
 def test_duplicate_blocked(self):
  self.run_provider([schema(),{'event_id':'e1'},event('error',None)])
  with self.assertRaises(FileExistsError):self.provider.generate(GeneratedVideoRequest('a'),self.root/'run')
  self.assertEqual(len(self.fake.calls),3)
 def test_post_error_no_retry(self):
  err=urllib.error.HTTPError(HOST,429,'limited',{},io.BytesIO(b'quota'))
  r=self.run_provider([schema(),err]);self.assertEqual(len(self.fake.calls),2)
  self.assertEqual(r.provenance['http_error']['status'],429)
 def test_schema_drift_no_post(self):
  r=self.run_provider([{}]);self.assertEqual(r.provenance['submission_calls'],0)
 def test_queue_disconnect_no_reconnect(self):
  r=self.run_provider([schema(),{'event_id':'e1'},b''])
  self.assertEqual(r.fallback,'LOCAL_MOTION_GRAPHIC');self.assertEqual(len(self.fake.calls),3)
 def test_timeout_bounded(self):
  times=iter([0,0,0,5,5])
  r=self.run_provider([schema()],timeout=1,clock=lambda:next(times,5))
  self.assertEqual(r.status,'LOCAL_MOTION_GRAPHIC')
 def test_cross_origin_output_blocked(self):
  r=self.run_provider([schema(),{'event_id':'e1'},event('complete',[{'video':{'url':'https://elsewhere.example/video.mp4'}}])])
  self.assertEqual(r.provenance['download_calls'],0)
 def test_transport_blocks_other_host(self):
  with self.assertRaises(VideoProviderError):PublicGradioTransport().open('GET','http://localhost/file')
 def test_router_fallback_local(self):
  p=HuggingFaceVideoProvider(dry_run=False,ffmpeg=self.ffmpeg,transport=Fake([{}]))
  r=AssetRouter().generate_video('test',GeneratedVideoRequest('a'),provider=p,output=self.root/'run')
  self.assertEqual(r.source_type,'local_graphic');self.assertEqual(r.status,'LOCAL_MOTION_GRAPHIC')
  self.assertTrue(r.sha256)
 def test_bad_container_rejected(self):
  p=self.root/'bad.mp4';p.write_bytes(b'not a video')
  with self.assertRaises(VideoProviderError):validate_video(p,self.ffmpeg,GeneratedVideoRequest('a'))
 def test_decode_metrics(self):
  p=self.root/'ok.mp4';p.write_bytes(b'\0\0\0\x18ftypisom')
  log='Duration: 00:00:04.00\n Stream #0:0: Video: h264, yuv420p, 576x1024, 30 fps\nframe= 120'
  with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'',log)):
   r=validate_video(p,self.ffmpeg,GeneratedVideoRequest('a'))
  self.assertEqual(r['fps'],30);self.assertEqual(r['width'],576)
 def test_failed_decode_rejected(self):
  p=self.root/'bad.mp4';p.write_bytes(b'\0\0\0\x18ftypisom')
  with patch('subprocess.run',return_value=subprocess.CompletedProcess([],1,'','')):
   with self.assertRaises(VideoProviderError):validate_video(p,self.ffmpeg,GeneratedVideoRequest('a'))
 def test_geometry_rejected(self):
  p=self.root/'bad.mp4';p.write_bytes(b'\0\0\0\x18ftypisom')
  log='Duration: 00:00:04.00\n Stream #0:0: Video: h264, yuv420p, 1280x720, 30 fps\nframe= 120'
  with patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,'',log)):
   with self.assertRaises(VideoProviderError):validate_video(p,self.ffmpeg,GeneratedVideoRequest('a'))
