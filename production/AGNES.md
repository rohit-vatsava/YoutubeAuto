# Agnes adapter audit — 2026-09-30

Sources reviewed (read only; no upstream scripts executed):
- https://github.com/uglylee/free-video-generator : core/api/agnes_video.py, core/api/rate_limiter.py, README, LICENSE
- https://wiki.agnes-ai.com/en/docs/agnes-video-25-flash.md
- https://wiki.agnes-ai.com/en/docs/agnes-video-25.md
- https://wiki.agnes-ai.com/en/docs/pricing.md
- https://wiki.agnes-ai.com/en/docs/terms-of-service.md
- https://agnes-ai.com/en/docs/agnes-video-v20 (marked retired)

## Findings and chosen behavior

| Topic | Finding / adapter behavior |
|---|---|
| Authentication | Bearer API key, server-side only; environment or local .env. No credentials in output. Redirects disabled on authenticated requests. |
| Video generation | POST https://apihub.agnes-ai.com/v1/videos. Use current agnes-video-2.5-flash; no paid-model fallback. |
| Image-to-video | Same endpoint, mode=keyframe with first_frame HTTPS URL. No implicit uploads. The reference uses a separate image-generation call to host local images; explicitly not adopted. |
| Polling | GET /agnesapi with video_id AND model_name. Public status/progress only; completed URL top-level or metadata.url. Never substitute task_id. Default 10 seconds, max 60 polls, 30-second HTTP timeout. |
| Rate limits | Reference assumes 20 shared requests/minute, reduces to 16; old official v2 catalog instead lists free executable 1 RPM. Neither is established as current 2.5 Flash quota. Current docs recommend 1–2 second polling and backoff on 429. Our conservative 10-second polling is local policy, not an account quota guarantee. Capture rate-limit/Retry-After headers; stop on error. |
| Output | MP4 URL, 720P only. Docs list vertical 720x1280; 16:9 is 1280x704. Supported duration 4–12 seconds, n=1. Actual resolution/duration must be measured from the file. Adapter returns REMOTE_REVIEW_REQUIRED with no local path. File import remains an explicit review step through existing local route(). |
| Errors | 400 validation, 401/403 authorization, 404 lookup, 429 limiting, 500 server failure, failed task, malformed/missing ID/URL, polling exhaustion all stop. Raw successful task responses retained; HTTP errors retain status/Retry-After only. |
| Retry semantics | Upstream retries POST after timeouts/429/5xx and changes frame counts after 400. Not adopted: no documented idempotency guarantee. Exactly one POST per persisted reservation, no automatic retry on POST or GET errors. Interrupted/ambiguous jobs are never silently resubmitted. |
| Pricing | Official Flash pricing is currently promotional $0/sec; regular 2.5 is paid. Eligibility/promotion can vary. Live requires explicit current free-account confirmation. No API price ceiling parameter is documented; client-side gate is not a server-enforced billing cap. |

## Licensing / usage

Reference code is MIT (copyright 2026 lcy362); this adapter is independently implemented from official documentation, not copied code. The MIT license is not a license for provider outputs. Agnes terms §8 make output ownership conditional on law and third-party rights; input/output may be used for service improvement unless an available opt-out applies. Users must hold input rights, comply with content rules, and avoid bypassing limits. AI labeling/traceability can be required. No blanket royalty-free or watermark-free guarantee was established from the current official API docs. Outputs stay UNCONFIRMED until reviewed. Do not send sensitive content for this smoke test.

## Commands

Dry run (no key/network needed):

```sh
.venv/bin/python tools/agnes_video.py
```

One live submission, only after confirming current free eligibility and adding AGNES_API_KEY to .env:

```sh
.venv/bin/python tools/agnes_video.py --live --free-access-confirmed
```

This fixed test uses a non-sensitive origami boat prompt, 4 seconds, vertical, 720P. Successful generation returns the remote URL for inspection; it does not automatically integrate unreviewed output into a production scene. Submission reservation is retained even after failure. Do not delete it or choose another directory to repeat this authorized single attempt.

Current audit execution: key missing in environment and .env; no live generation attempted. Requested latency, actual dimensions/duration/file size, watermark and visual quality remain unmeasured. No observed live rate limits and no paid calls.
