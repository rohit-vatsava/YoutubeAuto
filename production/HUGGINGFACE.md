# Public ZeroGPU video audit — 2026-09-30

Only public Hub metadata, pinned Space source, Gradio `/config` and `/gradio_api/info` were read. No upstream code was executed, UI scraped, or restrictions bypassed. Snapshots are in `reports/audits/huggingface/` (including complete input/output schemas).

## Candidates

| Space ID | Current metadata | Generation API / inputs | Modes and output | Queue/access | Visible licenses/constraints |
|---|---|---|---|---|---|
| `zerogpu-aoti/wan2-2-fp8da-aoti-faster` | RUNNING, ZeroGPU, public, ungated; Gradio 6.1.0 | `/generate_video`: image FileData, prompt, steps, negative_prompt, duration_seconds, guidance_scale, guidance_scale_2, seed, randomize_seed | Image REQUIRED. 0.5–5s control; frames=1+duration×16 clamped, max81 frames (~5.06s); 16fps MP4. Image-driven ratio, bounded480–832px (multiples16); square640. 9:16 input cropped to480x832. | Queue enabled, SSE; schema accessible anonymously. GPU dynamically budgeted. Public access does not ensure quota availability. | Wan official base Apache2; derivative transformer and Kijai LoRA repositories lack license metadata in the inspected cards. Do not infer all derivatives licensed by the base. |
| `Lightricks/ltx-video-distilled` | RUNNING, ZeroGPU, public, ungated; Gradio5.42.0 | `/text_to_video`, `/image_to_video`, `/video_to_video`; ordered schema below. Also media-dimension/task helper endpoints. | Text/image/video conditioning. Duration0.3–8.5s, frame snapping8n+1, max257 at30fps. Height/width256–1280 step32, configurable ratio;576x1024 exact9:16. H.264 MP4 VideoData + seed. | Queue enabled, SSE. Anonymous metadata/API exposure;60s xlarge GPU budget for≤7s requests (xlarge counts2× quota). No login gate in app source. Runtime can still reject anonymous calls. | LTX Open Weights0.X custom terms; acceptable-use restrictions and separate commercial licensing for entities with annual revenue≥$10M. Generated output and distribution need normal rights review. |
| `multimodalart/minimax-h3` | RUNNING, ZeroGPU, public, ungated; Gradio6.28.0 | `/generate`: prompt, image_path optional, last_image_path optional, canvas, duration, steps, seed, upsample. `/_fit_keyframe` helper. | Text or keyframes, synchronized audio/video MP4; UI2–14s, actual snapped17n+5 frames at24fps. Landscape/portrait/square/4:3/3:4/21:9 canvases; portrait544x960,640x1152,768x1344. | Queue enabled. **Internally calls `multimodalart/qwen3vl-conditioner` `/encode`** before video GPU work. Extra quota dependency, rejected for this one-Space test. | MiniMax-H3 community license; separate authorization above$20M yearly commercial revenue and model-display conditions for commercial services. Read exact license before commercial deployment. |

Source metadata links:
- https://huggingface.co/api/spaces/zerogpu-aoti/wan2-2-fp8da-aoti-faster
- https://huggingface.co/api/spaces/Lightricks/ltx-video-distilled
- https://huggingface.co/api/spaces/multimodalart/minimax-h3
- https://huggingface.co/Lightricks/LTX-Video/blob/main/LTX-Video-Open-Weights-License-0.X.txt
- https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE

## Selection

Choose **Lightricks/ltx-video-distilled** for this bounded attempt: model-owner Space, direct text-to-video, explicit API schema, native exact9:16 preset,30fps, no separate remote conditioning provider. Wan was reviewed first but requires image upload and ratio adjustment. MiniMax adds a second Space dependency. This is an operational choice, not an unmeasured quality ranking.

Official ZeroGPU documentation describes free access, anonymous2min daily quota/low priority, free accounts5min/medium, xlarge2× consumption. Paid account overage can consume credits automatically. Therefore this adapter intentionally sends **no HF token or cookies**, does not read cached HF credentials, never buys quota and does not use Inference Endpoints/Providers. A quota/authentication failure triggers fallback without another attempt.
https://huggingface.co/docs/hub/spaces-zerogpu

## Public API and exact smoke-test schema

Host: `https://lightricks-ltx-video-distilled.hf.space`

Schema: `GET /gradio_api/info`
Submit: `POST /gradio_api/call/text_to_video`
Queue stream: `GET /gradio_api/call/text_to_video/{event_id}`

The documented Gradio call protocol uses a single POST returning event_id, then an SSE GET with heartbeat/generating/complete/error events. No reconnect on disconnection; stop at terminal event.
https://www.gradio.app/guides/querying-gradio-apps-with-curl

Ordered data fields:

```text
prompt: string
negative_prompt: string
input_image_filepath: null
input_video_filepath: null
height_ui: 1024
width_ui: 576
mode: "text-to-video"
duration_ui: 4
ui_frames_to_use: 9
seed_ui: 42
randomize_seed: false
ui_guidance_scale: 1.0
improve_texture_flag: false
```

All submitted in `{"data":[...]}`. Output is `[VideoData, seed]`; VideoData.video is FileData with URL/path. Download only the returned same-origin HTTPS file once. No images required.

## Implementation boundaries

- `GeneratedVideoProvider` protocol and typed request/result sit at the existing explicit AssetRouter.generate_video boundary. Agnes remains unchanged.
- Dry-run default. Durable exclusive reservation prohibits a second submission in the same run directory, even after an ambiguous failure. Never delete it to repeat this authorized attempt.
-180s queue/download deadline checked at stream/chunk boundaries; per blocking read timeout≤30s (maximum deadline overrun one read timeout). Max10,000 SSE lines,1MB per line,100MB download. Local full decode timeout60s.
- No retries, redirects, provider switches, paid endpoints, hidden media uploads, or remote prompt enhancement.
- FFmpeg validates MP4, decodes all frames, checks dimensions, duration, fps and frame coverage; stores file SHA256 and provenance. Visual approval remains separate.
- Failure creates a local generic animated circuit SVG and routes it as `LOCAL_MOTION_GRAPHIC`, not generated video. It is a reusable asset fallback; no automatic modification of an existing M4 scene/spec.
- Space SHA is the audited source revision, not a guarantee the running public deployment remains fixed. Input schema drift fails closed before submission.
- Model licenses do not promise watermark-free results or factual accuracy. No generated text is used as factual evidence.

## Commands

```sh
.venv/bin/python tools/huggingface_video.py
.venv/bin/python tools/huggingface_video.py --live --ffmpeg /path/to/local/ffmpeg
```

The provided live smoke test is limited to this one Space, harmless abstract technical B-roll,4s,576x1024. The test uses a temporary FFmpeg installed via imageio-ffmpeg; no runtime SDK or provider dependencies were added to the repository. Supply `FFMPEG_BINARY` or `--ffmpeg` in a fresh environment.
