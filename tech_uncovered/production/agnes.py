"""Small Agnes video adapter. Independent implementation from official 2.5 docs.

No automatic submission retries, image uploads, paid model fallback, or SDK.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import urllib.request
import urllib.error
from urllib.parse import urlencode, urlparse

ROOT = 'https://apihub.agnes-ai.com'
FREE_MODEL = 'agnes-video-2.5-flash'


class AgnesError(RuntimeError):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_json(method, url, payload, key):
    """Exactly one HTTP attempt. Never forward credentials through redirects."""
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=30) as response:
            result = json.loads(response.read(2_000_000))
            headers = {k: v for k, v in response.headers.items()
                       if k.lower().startswith('x-ratelimit') or k.lower() == 'retry-after'}
            return result, headers
    except urllib.error.HTTPError as exc:
        # Do not expose raw responses or credentials in logs.
        raise AgnesError(f'HTTP {exc.code}; Retry-After={exc.headers.get("Retry-After", "unspecified")}; no retry') from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise AgnesError(f'{type(exc).__name__}; outcome may be unknown; no retry') from None


@dataclass(frozen=True)
class AgnesVideoRequest:
    prompt: str
    seconds: int = 4
    aspect_ratio: str = '9:16'
    first_frame: str | None = None

    def payload(self):
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise ValueError('Nonempty prompt required')
        if type(self.seconds) is not int or not 4 <= self.seconds <= 12:
            raise ValueError('Duration must be an integer from 4 to 12')
        if self.aspect_ratio not in ('21:9', '16:9', '4:3', '1:1', '3:4', '9:16'):
            raise ValueError('Unsupported aspect ratio')
        data = dict(model=FREE_MODEL, prompt=self.prompt, seconds=str(self.seconds),
                    aspect_ratio=self.aspect_ratio, size='720P', n=1,
                    mode='keyframe' if self.first_frame else 'text')
        if self.first_frame:
            parsed = urlparse(self.first_frame)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Image input must be an explicitly supplied public HTTPS URL; no uploads')
            data['first_frame'] = self.first_frame
        return data


class AgnesVideoProvider:
    """Dry-run by default; each live output directory permits only one submission.

    A failed/ambiguous attempt keeps its reservation. Polling never submits jobs.
    Free-account eligibility must be confirmed externally against current pricing.
    """
    def __init__(self, api_key='', *, dry_run=True, free_access_confirmed=False,
                 transport=request_json, sleep=time.sleep, clock=time.monotonic,
                 max_polls=60, poll_seconds=10):
        if not 1 <= max_polls <= 180 or not 2 <= poll_seconds <= 60:
            raise ValueError('Polling bounds invalid')
        self.api_key = api_key
        self.dry_run = dry_run
        self.free_access_confirmed = free_access_confirmed
        self.transport, self.sleep, self.clock = transport, sleep, clock
        self.max_polls, self.poll_seconds = max_polls, poll_seconds

    def generate(self, request, output):
        payload = request.payload()
        report = dict(provider='agnes', request=payload, status='DRY_RUN',
                      generation_calls=0, polling_calls=0, estimated_cost_usd=0,
                      actual_cost_usd=None, output_resolution=None, duration_seconds=None,
                      file_size_bytes=None, watermark_status='NOT_INSPECTED',
                      quality_notes='No generated file inspected', api_limits_observed=[],
                      license_status='UNCONFIRMED', latency_seconds=None)
        output = Path(output)
        output.mkdir(parents=True, exist_ok=True)
        if self.dry_run:
            (output / 'dry-run.json').write_text(json.dumps(report, indent=2))
            return report
        if not self.api_key:
            raise AgnesError('AGNES_API_KEY missing; no request made')
        if not self.free_access_confirmed:
            raise AgnesError('Current free account eligibility must be confirmed; no request made')
        # Exclusive, durable reservation BEFORE POST; blocks crash-driven duplicates.
        with (output / 'submission-reserved.json').open('x') as handle:
            json.dump(dict(request=payload, reserved_at=datetime.now(timezone.utc).isoformat()), handle)
        started = self.clock()
        def persist():
            report['latency_seconds'] = self.clock() - started
            temp = output / 'result.tmp'
            temp.write_text(json.dumps(report, indent=2))
            temp.replace(output / 'result.json')
        try:
            report['generation_calls'] = 1
            report['status'] = 'SUBMITTING'
            persist()
            created, headers = self.transport('POST', ROOT + '/v1/videos', payload, self.api_key)
            report['api_limits_observed'].append(headers)
            report['create_response'] = created
            video_id = created.get('video_id')
            if not isinstance(video_id, str) or not video_id:
                raise AgnesError('Missing video_id; do not resubmit or substitute task_id')
            report['video_id'] = video_id
            persist()
            for _ in range(self.max_polls):
                self.sleep(self.poll_seconds)
                report['polling_calls'] += 1
                result, headers = self.transport('GET', ROOT + '/agnesapi?' + urlencode(
                    dict(video_id=video_id, model_name=FREE_MODEL)), None, self.api_key)
                report['api_limits_observed'].append(headers)
                report['last_response'] = result
                status = str(result.get('status', '')).lower()
                report['status'] = status.upper()
                persist()
                if status == 'completed':
                    url = result.get('url') or (result.get('metadata') or {}).get('url')
                    parsed = urlparse(url or '')
                    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
                        raise AgnesError('Completed response lacks HTTPS output URL')
                    report['output_url'] = url
                    report['provider_reported_size'] = result.get('size')
                    report['provider_reported_seconds'] = result.get('seconds')
                    persist()
                    return report
                if status == 'failed':
                    raise AgnesError('Provider task failed; see persisted response; no retry')
                if status not in ('queued', 'pending', 'in_progress'):
                    raise AgnesError('Unknown task status; no retry')
            raise AgnesError('Polling limit reached; existing job may still complete; no resubmission')
        except Exception as exc:
            report['status'] = 'STOPPED'
            report['error'] = str(exc) if isinstance(exc, AgnesError) else type(exc).__name__
            persist()
            raise
