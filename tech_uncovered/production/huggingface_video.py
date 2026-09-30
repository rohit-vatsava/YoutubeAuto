"""One audited public ZeroGPU Space via documented Gradio /call API.

Anonymous only: no stored HF credentials, credits, paid endpoints, SDK retries,
provider switching, or hidden downloads. The endpoint/schema are pinned.
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse
import hashlib
import json
import math
import re
import subprocess
import time
import urllib.request
import urllib.error

SPACE_ID = 'Lightricks/ltx-video-distilled'
SPACE_SHA = '8a42e93469c66b62d794b83a4233f5fc8439e2b5'
HOST = 'https://lightricks-ltx-video-distilled.hf.space'
ENDPOINT = '/text_to_video'
PARAMETERS = ['prompt', 'negative_prompt', 'input_image_filepath', 'input_video_filepath',
              'height_ui', 'width_ui', 'mode', 'duration_ui', 'ui_frames_to_use',
              'seed_ui', 'randomize_seed', 'ui_guidance_scale', 'improve_texture_flag']


@dataclass(frozen=True)
class GeneratedVideoRequest:
    prompt: str
    seconds: float = 4
    width: int = 576
    height: int = 1024
    seed: int = 42

    def data(self):
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError('Prompt required')
        if not math.isfinite(self.seconds) or not 2 <= self.seconds <= 5:
            raise ValueError('B-roll duration must be 2–5 seconds')
        if (self.width, self.height) != (576, 1024):
            raise ValueError('Audited preset is 576x1024, exact 9:16')
        if type(self.seed) is not int or not 0 <= self.seed < 2**32:
            raise ValueError('Invalid seed')
        return [self.prompt, 'blurry, jittery, distorted, text, logos, watermark', None, None,
                self.height, self.width, 'text-to-video', self.seconds, 9, self.seed,
                False, 1.0, False]


@dataclass
class GeneratedVideoResult:
    status: str
    path: str | None = None
    metrics: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    error: str | None = None
    fallback: str | None = None
    def to_dict(self):
        return asdict(self)


class GeneratedVideoProvider(Protocol):
    def generate(self, request: GeneratedVideoRequest, output: Path) -> GeneratedVideoResult: ...


class VideoProviderError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PublicGradioTransport:
    def open(self, method, url, payload=None, timeout=30):
        # Same Space only, including returned files. Redirects cannot switch providers.
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.netloc != urlparse(HOST).netloc:
            raise VideoProviderError('Cross-origin request refused')
        request = urllib.request.Request(url, method=method,
                    data=None if payload is None else json.dumps(payload).encode(),
                    headers={'Content-Type': 'application/json'})
        return urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout)


def validate_video(path, ffmpeg, request):
    """Decode entire local file, then inspect decoded stream metadata. Never fetch URLs."""
    path = Path(path).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= 100_000_000:
        raise VideoProviderError('Missing/oversized video')
    with path.open('rb') as f:
        if f.read(12)[4:8] != b'ftyp':
            raise VideoProviderError('Result is not an MP4 container')
    run = subprocess.run([str(ffmpeg), '-nostdin', '-v', 'info', '-xerror',
        '-protocol_whitelist', 'file,pipe', '-i', str(path), '-map', '0:v:0',
        '-f', 'null', '-'], capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise VideoProviderError('Video full-decode validation failed')
    stream = next((s for s in run.stderr.splitlines() if 'Stream #' in s and 'Video:' in s), '')
    dims = re.search(r'\b(\d{2,5})x(\d{2,5})\b', stream)
    fps = re.search(r'([\d.]+) fps', stream)
    duration = re.search(r'Duration: (\d+):(\d+):([\d.]+)', run.stderr)
    frames = re.findall(r'frame=\s*(\d+)', run.stderr)
    if not all((dims, fps, duration, frames)):
        raise VideoProviderError('Incomplete decoded video metadata')
    w, h = map(int, dims.groups())
    seconds = int(duration[1])*3600 + int(duration[2])*60 + float(duration[3])
    rate = float(fps[1])
    if (w,h) != (request.width, request.height) or not 1 <= rate <= 60 or abs(seconds-request.seconds) > .4:
        raise VideoProviderError('Output geometry/duration/fps mismatch')
    if abs(int(frames[-1])/rate-seconds) > .2:
        raise VideoProviderError('Decoded frame count does not cover duration')
    return dict(width=w,height=h,duration_seconds=seconds,fps=rate,frames=int(frames[-1]),
                file_size_bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                full_decode_passed=True,watermark='UNCLEAR_PENDING_VISUAL_REVIEW')


def local_motion_graphic(output):
    path = Path(output)/'local-motion-graphic.svg'
    path.write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="576" height="1024" viewBox="0 0 576 1024">
<rect width="576" height="1024" fill="#081321"/>
<path d="M100 300H476V724H100Z M100 512H476 M288 300V724" fill="none" stroke="#245367" stroke-width="4"/>
<circle cx="100" cy="512" r="12" fill="#36d8c3"><animate attributeName="cx" values="100;476;100" dur="4s" repeatCount="indefinite"/></circle>
</svg>''')
    return str(path.resolve())


class HuggingFaceVideoProvider:
    def __init__(self, *, dry_run=True, ffmpeg=None, timeout=180,
                 transport=None, clock=time.monotonic, validator=validate_video):
        if not 1 <= timeout <= 600:
            raise ValueError('Timeout must be 1–600 seconds')
        self.dry_run, self.ffmpeg, self.timeout = dry_run, ffmpeg, timeout
        self.transport, self.clock = transport or PublicGradioTransport(), clock
        self.validator = validator

    def generate(self, request, output):
        payload = {'data': request.data()}
        output = Path(output); output.mkdir(parents=True, exist_ok=True)
        provenance = dict(provider='huggingface',space_id=SPACE_ID,space_sha=SPACE_SHA,
            endpoint=ENDPOINT,request=asdict(request),payload=payload,anonymous=True,
            paid_fallback=False,license='LTX-Video-Open-Weights-License-0.X',
            license_review_required=True,submission_calls=0,queue_calls=0,download_calls=0,
            events=[],actual_cost_usd=0)
        if self.dry_run:
            result = GeneratedVideoResult('DRY_RUN', provenance=provenance)
            (output/'dry-run.json').write_text(json.dumps(result.to_dict(),indent=2))
            return result
        if not self.ffmpeg or not Path(self.ffmpeg).is_file():
            raise ValueError('Local FFmpeg required BEFORE live submission')
        # Refuse repeat across process restarts, including an ambiguous failed POST.
        with (output/'submission-reserved.json').open('x') as f:
            json.dump(provenance, f, indent=2)
        started = self.clock()
        def persist(result):
            provenance['latency_seconds'] = self.clock()-started
            temp = output/'result.tmp';temp.write_text(json.dumps(result.to_dict(),indent=2))
            temp.replace(output/'result.json')
        result = GeneratedVideoResult('PRECHECK',provenance=provenance)
        def remaining():
            value = self.timeout-(self.clock()-started)
            if value <= 0: raise VideoProviderError('Queue deadline exceeded; no reconnect/resubmit')
            return min(30,value)
        try:
            # Public metadata GET only. Schema drift fails closed before inference.
            with self.transport.open('GET', HOST+'/gradio_api/info', timeout=remaining()) as response:
                info = json.loads(response.read(2_000_000))
            params = info.get('named_endpoints',{}).get(ENDPOINT,{}).get('parameters',[])
            if [p.get('parameter_name') for p in params] != PARAMETERS:
                raise VideoProviderError('Public input schema changed')
            provenance['submission_calls'] = 1; result.status='SUBMITTING';persist(result)
            base = HOST+'/gradio_api/call'+ENDPOINT
            with self.transport.open('POST',base,payload,remaining()) as response:
                provenance['submission_http_status'] = response.status
                created = json.loads(response.read(100_000))
            event_id = created.get('event_id','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',event_id):
                raise VideoProviderError('Missing/invalid event_id; no resubmission')
            provenance['event_id'] = event_id; result.status='QUEUED';persist(result)
            provenance['queue_calls'] = 1
            completed = None
            with self.transport.open('GET',base+'/'+event_id,timeout=remaining()) as response:
                event = ''; data = []
                for _ in range(10000):
                    remaining()
                    raw = response.readline(1_000_001)
                    if not raw: break
                    if len(raw)>1_000_000: raise VideoProviderError('Oversized queue event')
                    line = raw.decode('utf-8').rstrip('\r\n')
                    if line.startswith('event:'): event=line[6:].strip()
                    elif line.startswith('data:'): data.append(line[5:].strip())
                    elif not line and event:
                        body=json.loads('\n'.join(data)) if data else None
                        provenance['events'].append({'event':event,'data':body})
                        persist(result)
                        if event=='error': raise VideoProviderError('Space queue error: '+json.dumps(body))
                        if event=='complete': completed=body;break
                        if event not in ('heartbeat','generating'): raise VideoProviderError('Unknown queue event')
                        event='';data=[]
            if completed is None: raise VideoProviderError('Queue ended without success; no reconnect')
            file = completed[0]['video']
            url=file.get('url')
            if not url or urlparse(url).netloc != urlparse(HOST).netloc or urlparse(url).scheme!='https':
                raise VideoProviderError('Missing or cross-origin output URL')
            target=output/'generated.mp4'
            provenance['download_calls']=1;persist(result)
            with self.transport.open('GET',url,timeout=remaining()) as response, target.open('xb') as f:
                size=0
                while True:
                    remaining();chunk=response.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk)
                    if size>100_000_000: raise VideoProviderError('Download exceeds 100 MB')
                    f.write(chunk)
            result.metrics=self.validator(target,self.ffmpeg,request)
            result.path=str(target.resolve());result.status='VALIDATED_REVIEW_REQUIRED'
        except Exception as exc:
            if isinstance(exc,urllib.error.HTTPError):
                detail=exc.read(10000).decode('utf-8',errors='replace')
                provenance['http_error']={'status':exc.code,'body':detail,'retry_after':exc.headers.get('Retry-After')}
                result.error=f'HTTP {exc.code}; no retry'
            else: result.error=str(exc)
            result.status='LOCAL_MOTION_GRAPHIC';result.fallback='LOCAL_MOTION_GRAPHIC'
            result.path=local_motion_graphic(output)
        persist(result)
        return result
