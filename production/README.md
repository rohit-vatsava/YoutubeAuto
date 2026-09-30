# M4 local production attachments

Run from the repository root. No provider calls are made by these commands:

```sh
.venv/bin/python main.py produce --fixture fixtures/production/astra-revision-7/fixture.json --preview --avatar fixtures/production/astra-revision-7/avatar.json --output reports/production/astra-revision-7-final
node tools/render_production.mjs --spec reports/production/astra-revision-7-final/production-spec.json --render
```

The revision-7 fixture preserves the saved M3 narration and provenance. Its WAV is silence and its word/sentence timings are deterministic estimates, not measured speech. The local Canvas/WebCodecs renderer exports a silent MP4. `CHROME_PATH` and `PLAYWRIGHT_MODULE` can override local browser/runtime paths.

## Recorded narration

Pass `--narration local-narration.json` to `produce` to import a `NarrationResult`. Its fields are audio_path, duration_seconds, words, sentences, provider, model_voice_id, and provenance. Word entries contain text, start_seconds, end_seconds, sentence_id, and optional emphasis. Sentence entries contain sentence_id, text, start_seconds, and end_seconds. Preserve exact M3 sentence IDs/text. Provenance must include script_sha256 (SHA-256 of full_script UTF-8) and audio_sha256. See the fixture and narration.py for the exact serialized contract. Local WAV duration is checked against timestamps. No external provider is implemented.

Audio timing drives scene boundaries and phrase captions; estimated timing remains the fallback. Phrase timestamp quantization tolerance is one frame. Real recordings must fit the 45–60 second target. Narration must be re-aligned if the recording changes.

## Avatar attachment

Supply `--avatar local-avatar.json`. See fixtures/production/astra-revision-7/avatar.json. Set source_path to a local image, supply provenance/licensing information, and choose position left/right/center and width_fraction 0.2–0.4. Crop coordinates are normalized. Set transparent_background true for a cutout, otherwise the image is masked. Style and version are descriptive metadata. No avatar or likeness is created here.

The host appears for three seconds at opening and closing. Other scenes remain independent. Actual narration controls the storyboard timing, so the example's scene boundaries differ from the suggested approximate storyboard.

## Audio and assets

AudioMix describes narration/music gains, music fades/ducking, SFX cues, and limiter/normalization targets. No music or SFX are supplied. Limiter/LUFS values are metadata, not an implemented mastering processor. The Remotion composition wires local audio tracks; its dependencies are not installed in this environment, so audio rendering remains unverified here. The tested local renderer remains silent. Remotion requires the production output directory as its public directory so copied assets resolve.

AssetRouter supports local files and explicit placeholders for future asset sources; it never downloads. ProductionSpec and Creative DNA include retention metadata. These are descriptive outputs, not automatic optimization.

Before a finished audiovisual Short: provide a licensed/authorized avatar image and recorded narration with matching alignment, render with an audio-capable environment, then inspect the actual audio and image result. Placeholder safety checks do not substitute for that review.
