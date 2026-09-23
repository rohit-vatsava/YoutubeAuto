<<<<<<< HEAD
# YoutubeAuto
YoutubeAutomation personal project 
=======
# Tech Uncovered — Radar and Intelligence

## Module 1 — Radar

Radar collects public competitor video metadata through the **official YouTube Data API v3**, stores observations in SQLite, and produces explainable outlier and recurring-theme reports. Positioning: interesting AI, software, computing, and technology stories explained quickly, clearly, and visually.

Radar V1 is competitor research only. Radar retrieves no transcripts and includes no scraping, browser automation, script writing, voiceover, video production, uploading, scheduling, or own-channel analytics. Module 2, documented below, accepts locally supplied transcript/context packets. The reference repository is not a dependency. No reference scripts are executed.

## Setup

Python 3.11 or newer is required. From this repository:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
cp .env.example .env
```

For Windows activation, use `.venv\Scripts\activate`.

### YouTube API key

1. Open [Google Cloud Console](https://console.cloud.google.com/), and create or select a project.
2. In **APIs & Services → Library**, find **YouTube Data API v3** and enable it for that project.
3. Open **APIs & Services → Credentials → Create credentials → API key**.
4. Edit the key and set **API restrictions → Restrict key → YouTube Data API v3**. Save. If using a fixed outbound IP, you may also restrict the key to that IP; browser-referrer restrictions are inappropriate for this local CLI.
5. Edit `.env` locally and set:

   ```dotenv
   YOUTUBE_API_KEY=your_actual_key
   ```

6. Run `python main.py research`.

No OAuth client, YouTube login, or channel-owner access is required for these public endpoints. Do not paste your key into chat or commit it. `.env`, generated reports, databases, and `.venv` are gitignored. Existing environment variables take precedence over `.env`. Request URLs and credentials are not logged or used as cache keys.

See [Google's setup guide](https://developers.google.com/youtube/v3/getting-started). Credential validity and actual Google Cloud quota have not been verified by the synthetic test suite.

## Commands

```bash
# Live collection; default output is reports/ and data/intelligence.sqlite3
python main.py research

# Replay stored observations, no network and no API key
python main.py research --offline

# Explicitly bypass API cache
python main.py research --refresh

# Synthetic example: no API key, no network, isolated demo database and reports
python main.py research --fixture tests/fixtures/synthetic.json

# Tune collection and minimum sample requirements
python main.py research --max-uploads 100 --lookback-days 90 --min-sample 10 --request-budget 100

# Full test suite; standard library unittest, no network or credentials
python -m unittest discover -v
```

Additional options: `--db`, `--reports-dir`, `--channels`, `--themes`. `--offline` and `--fixture` are mutually exclusive and cannot be combined with `--refresh`. Synthetic defaults are `data/demo.sqlite3` and `reports/demo/`; do not point synthetic runs at your live database. Fixture time is fixed, making scoring reproducible. Run IDs and generation metadata may differ between runs.

Exit codes: **0** complete, **1** configuration/local input error, **2** partial API collection failure. A partial run writes clearly labelled reports for successfully collected observations; it never silently substitutes previous data for a failed API batch. A missing resource is recorded in warnings; if previously stored, it is marked unavailable with statistics cleared. A never-seen missing resource has no invented metadata.

The CLI prints channels/videos processed, top 10 qualifying outliers, strongest recurring themes, quota estimate, cache hit rate, and failures. Fewer than ten qualifying outliers is a valid result. `channels_processed` counts channels whose identity and upload list were retrieved; video-batch failures are reported separately.

## Competitors and API boundary

`config/channels.json` contains Fireship, Futurepedia, The AI Grid, AI Explained, Two Minute Papers, and ColdFusion. Handles are resolved by `channels.list(forHandle=...)` into channel IDs and uploads playlists, and stored in SQLite. Futurepedia uses `@futurepedia_io`, linked from [its website](https://www.futurepedia.io/about-us). Other handles link directly to the named YouTube channels. The first live run validates current API resolution; handles may change. A verified `channel_id` can replace handle lookup in config.

Flow: `cli → research.collect → YouTubeClient → SQLite → score_videos → TopicClassifier → reports`.

`tech_uncovered/youtube.py` is the only live network boundary. It uses channels, playlistItems, and videos endpoints under `https://www.googleapis.com/youtube/v3/`. There is no search or scraping fallback. Upload playlists are paginated; video IDs are deduplicated and requested in batches of 50 across channels. Stored fields include video ID, title, channel ID/name, publication date, views, nullable likes/comments, duration seconds, URL, observation timestamp, availability, and live status. Comments means **comment count**, not comment text.

Defaults collect the latest 100 uploads per channel. Scores use eligible observations aged 1–90 days. Collection caps and sparse samples are visible. Offline replay selects the latest stored uploads per configured channel up to the current cap; it is a replay of retained observations, not a statement about current availability.

## Scoring contract (version 1.0)

The overall channel median is reported for context. Ranking baselines are computed separately for each **channel ID + duration cohort**:

- `short_candidate`: duration 1–180 seconds.
- `longer_video`: duration over 180 seconds.

Duration is not a definitive Shorts classification. The public API does not expose a reliable Shorts flag or competitor file dimensions. A 100-second horizontal explainer belongs in `short_candidate` and is not asserted to be a Short.

Exclude identifiable current, upcoming, and archived livestreams, unavailable videos, invalid/missing views or duration, future publication dates, and videos outside the age window. **Under 24 hours is provisional and excluded from both the baseline and main ranking.** Baselines include the candidate itself and require at least 10 eligible videos. No fallback across channels or cohorts occurs. Ten to nineteen observations are labelled a small sample.

```text
age_days = (observed_at - published_at).total_seconds() / 86400
views_per_day = views / max(age_days, 1)
M = median(cohort views)
D = median(cohort views_per_day)
outlier_ratio = views / M
velocity_ratio = views_per_day / D
velocity_adjusted_score = sqrt(outlier_ratio * velocity_ratio)
```

The median of rates is calculated directly, not as median views divided by median age. Equal weighting in log space balances accumulated performance and lifetime average pace. Example: 200,000 views at 10 days against M=100,000 and D=5,000 yields ratios 2 and 4, and score √8 = 2.8284.

**If baseline sample size is below the minimum, every ratio, score, and percentile is NULL**, with `insufficient_baseline_sample`. Zero baseline denominators also produce NULL with `zero_baseline_median`. Missing counts stay NULL; genuine zero views remain valid. Other reasons: `under_24_hours`, `outside_lookback`, `future_publish_date`, `unavailable`, `live_or_upcoming`, `missing_or_invalid_views`, `missing_or_invalid_duration`, or `eligible`.

A qualifying outlier has both raw outlier ratio ≥2 and adjusted score ≥2. Eligible videos rank globally by adjusted score descending, then raw ratio descending, then video ID ascending. Ranking is descriptive across duration cohorts, not proof of identical audience behavior.

Within-channel/cohort percentile uses adjusted scores and the midrank definition:

```text
100 * (number of strictly lower scores + 0.5 * number of tied scores) / sample size
```

All ties receive the same percentile. An all-tied cohort has percentile 50; the highest value need not equal 100. Scores are persisted unrounded. Each video also carries both baseline medians, baseline sample size, provisional flag, and eligibility reason. Under-minimum baselines may retain descriptive medians, but no scores.

`observed_at` is when statistics were fetched, and remains unchanged on a cache hit. This keeps cached scores stable instead of dividing old view counts by today's age. Views/day is **lifetime average pace**, not a recent view delta. The formula does not model nonlinear growth or predict virality.

## Topic classification

`TopicClassifier` is a Python Protocol with `name`, `version`, and `classify(video: dict) -> list[str]`. `analyze` accepts any implementation of that interface. A later classifier can be injected without changing collection, scoring, or report generation. No LLM provider or credentials are included.

The V1 `DictionaryTopicClassifier` uses case-insensitive phrase matching against titles and editable `config/themes.json`. It groups the top 30 qualifying outliers and requires at least two distinct videos per recurring theme. Groups are ordered by channel breadth, video count, and median score. A video can belong to multiple themes. Unmatched videos remain unclassified; no theme is invented to fill a report. Titles with little information produce weaker topic coverage.

`top_topics.md` uses neutral subject labels and supporting channel/video links, not proposed titles, hooks, scripts, or copied video concepts. It reports observed associations, not causes or validated recommendations for Tech Uncovered.

## Outputs and downstream modules

Live output paths:

```text
reports/outliers.csv
reports/outliers.json
reports/top_topics.md
```

Despite its filename, CSV contains **all processed videos**, including ineligible/provisional rows with empty score cells. Filter `is_outlier=True` for qualifying outliers; use `rank` for the ranking of all eligible videos. Text fields beginning with spreadsheet formula markers are prefixed with an apostrophe in CSV. JSON preserves original titles.

JSON is the recommended downstream interface. It contains:

- `schema_version: "1.0"`, `module: "Radar"`, `score_version: "1.0"`, run ID and generation timestamp.
- `metadata`: settings, mode (`live`, `offline`, `synthetic`), status, channels, classifier identity, quota/cache counters, warnings, and partial failures.
- `baselines`: channel/cohort medians and sample sizes.
- `videos`: every processed observation plus all score fields.
- `outliers`: qualifying subset in rank order.
- `topics`: neutral themes with evidence IDs/URLs and supporting statistics.

Later modules should check version, mode, and status, and join on stable `video_id`/`channel_id`. They should not consume synthetic records as live evidence. No later module is implemented.

Radar bootstraps schema version 1; versioned migrations upgrade through Intelligence (2) to Research + Scripts (3), recorded in `PRAGMA user_version`. Radar tables: channels, videos (latest observation), api_cache, research_runs, baselines, video_scores, and topic_groups. Score fields are explicit SQL columns, with the complete per-video result additionally in JSON. Reports are replaced atomically **per file**; the three-file bundle is not transactional. JSON and Markdown include run IDs to identify provenance. Database writes complete before exports.

## Quota, caching, and retention

Channel resolution has a 7-day cache. Upload listings and video responses have a 6-hour cache. Identical repeat runs inside cache lifetime make zero requests. Changed batch composition can cause a new video request. Failed requests are never cached. Transient network/429/5xx errors receive at most three attempts with backoff. Quota exhaustion stops further requests; a per-run budget defaults to 100 attempts.

For six channels ×100 uploads, a full initial run typically needs 6 channel calls +12 playlist calls +12 video calls = **30 units**, before retries. These list endpoints currently cost one unit per call. [Google quota table](https://developers.google.com/youtube/v3/determine_quota_cost).

The CLI reports conservatively estimated units used, counting request attempts. It cannot read actual account-wide quota usage; verify that in Cloud Console. Cache hit rate counts cache lookups, not retries.

API data retention and derived-metric permission are documented uncertainties, not software gates. Current [YouTube developer policies](https://developers.google.com/youtube/terms/developer-policies) restrict derived metrics by default, with an [analytics amendment/application process](https://developers.google.com/youtube/terms/derived-metrics-policy) addressing custom scores and categorization. A working API key does not establish permission for this use. Confirm applicable requirements for your project. Reports clearly distinguish Radar heuristics from YouTube metrics. All scoring tests and synthetic examples work independently of live permission or credentials.

On non-synthetic runs, stored source observations/cache records older than 30 days are pruned. Saved run results expire using their oldest video observation timestamp, so replay cannot extend the life of old statistics. Current reports are overwritten on successful export; metadata is refreshed through normal cache expiry. Cleanup only happens when invoked: this CLI has no scheduler. If you stop using Radar, delete retained databases/reports by the applicable deadline. Manually copied reports/backups are your responsibility. Synthetic data is explicitly labelled and does not need API retention cleanup.

## Tests and limitations

The standard-library test suite exercises scoring, age boundaries, ties, zero/missing values, thin cohorts, live/format exclusions, classifier substitution, cache expiry/reuse, pagination, bounded retries, quota stops, partial collection, persistence, retention, CSV escaping, and the network-free fixture CLI. API responses in tests are fake; they do not verify live credentials, handle availability, or YouTube schema changes.

No claim of predictive validation is made. A minimum sample of 10 and the outlier threshold are tunable heuristics. Sparse short-video cohorts may produce no scores. Missing/private/deleted uploads and collection caps limit coverage. Topic matching uses titles only. Reports may combine slightly different observation times from cached batches; every row exposes its timestamp. Independent processes writing the same output directory concurrently are not supported. Run a single CLI process per database/report directory.

## Reference attribution

Inspired by Jake Schincariol's [youtube-agent-skill](https://github.com/Jakeschincariol/youtube-agent-skill), published under MIT. Reviewed `skills/yt-viral/swipe.py`, `skills/yt-viral/SKILL.md`, `skills/yt-script/hookscore.py`, `skills/yt-script/hooks.json`, and `skills/yt-script/SKILL.md`.

Adapted ideas: own-channel median normalization; avoid inventing numbers; distinguish title patterns from performance explanations. Radar independently implements its scoring and adds age adjustment, format cohorts, null eligibility, caching, and official API collection. No upstream source code or hook dictionary is copied.

The reference hook scorer combines specificity, address, stakes, curiosity, and brevity using 60% mean +40% minimum. Its own documentation warns that it barely distinguishes a creator's hits from misses. Hook scoring is therefore not part of V1 performance ranking. Claude-specific packaging, slash commands, script generation, and transcript tools are omitted.

# Module 2 — Intelligence

Intelligence turns one immutable Radar run into evidence-labelled story briefs, conservative trend clusters, and original adjacent investigation ideas. It does not write scripts or call an LLM, transcript website, search engine, or any other network service. It does not scrape. All four provider interfaces are replaceable without changing the pipeline: `TranscriptProvider`, `ResearchProvider`, `IdeaGenerator`, and `SimilarityChecker`.

## Run Intelligence

```bash
# Latest complete live Radar run; no extra YouTube/API requests
python main.py intelligence --offline

# Select an exact historical Radar snapshot (never substitutes another run)
python main.py intelligence --offline --run-id bbfbe5b1-73cf-4c78-a537-fb84186d97f6 --top 10

# Add locally supplied context and evidence
python main.py intelligence --offline --context-file context/videos.json --evidence-file evidence/claims.json

# Retrieve local context anew and create another immutable result
python main.py intelligence --offline --refresh-context --context-file context/videos.json

# Fully fictional, reproducible demonstration in its own database/output directory
python main.py intelligence --offline \
  --fixture tests/fixtures/intelligence/radar.json \
  --context-file tests/fixtures/intelligence/context.json \
  --evidence-file tests/fixtures/intelligence/evidence.json \
  --top 9

# Complete combined test suite
python -m unittest discover -v
```

Default `--top` is 20 **eligible** videos ranked by adjusted Radar score, including eligible videos that do not cross Radar's strong-outlier threshold. Provisional and score-ineligible records are excluded. Candidate records come only from `video_scores.payload` for the selected run, never current `videos` rows. The original source snapshot hash is preserved. Latest means most recently inserted complete live run; an explicit run ID may select a partial/offline/synthetic run and its provenance is retained. Non-synthetic observations older than 30 days cannot be reprocessed; collect fresh Radar data instead. No alternative run is silently substituted.

Additional options: `--db`, `--reports-dir`, `--config`. Fixture mode defaults to `data/intelligence-demo.sqlite3` and `reports/intelligence-demo/`, fixes the analysis clock to the fixture timestamp, and refuses to mix fictional data into a database containing live Radar runs. Default mode uses the existing `data/intelligence.sqlite3` and `reports/intelligence/`. Omit `--offline` if desired: current providers remain entirely local. Future providers must honor the protocol's `offline` parameter. `--refresh-context` passes a refresh instruction to the provider; local files are reread on every CLI invocation anyway, without a network cache or an update to historical records.

## Context and evidence inputs

The fixtures are complete examples of the input schemas. A context file has a `videos` mapping keyed by video ID. Each entry may contain:

```json
{
  "videos": {
    "video-id": {
      "source": "User-supplied transcript or editorial packet",
      "provenance_note": "Why we have permission to use this material",
      "language": "en",
      "text": "Supplied transcript text; never fabricated",
      "segments": [{"start": 0, "text": "Optional normalized transcript segment"}],
      "context": {
        "canonical_subject": "A precise product/version or underlying subject",
        "core_event": "The event to investigate",
        "context_summary": "A short neutral description of the competitor's framing",
        "competitor_angle": "demonstration",
        "evergreen_or_news": "news",
        "event_key": "specific-product-version-event",
        "products_models": ["Specific product version"],
        "claims": [{"claim_id": "unique-claim-id", "text": "A material claim", "material": true}]
      }
    }
  }
}
```

Other StoryBrief fields can be supplied under `context`; see `models.py` and the fixture. Transcript text/segments need a source and provenance note. Structured context can be supplied without a transcript. Raw transcript availability alone does **not** imply that the deterministic extractor understands the story; it remains context-limited without adequate structured context. V1 does not perform general natural-language transcript summarization.

Evidence files have `sources` and `assessments` mappings:

```json
{
  "sources": {
    "source-id": {
      "reference": "https://publisher.example/source",
      "publisher": "Publisher name",
      "source_type": "PRIMARY",
      "relation": "SUPPORTS",
      "excerpt": "The exact relevant supporting passage"
    }
  },
  "assessments": {
    "unique-claim-id": {
      "claim_text": "A material claim",
      "status": "VERIFIED",
      "evidence_ids": ["source-id"],
      "assessed_by": "Human reviewer",
      "rationale": "How the passage supports this exact claim"
    }
  }
}
```

Evidence is manually supplied and assessed, not fetched or independently fact-checked by this module. URLs alone never verify a claim. Claim text must match exactly. Source type is PRIMARY or SECONDARY; relation is SUPPORTS or CONTRADICTS. Status is VERIFIED, PARTIALLY_VERIFIED, UNVERIFIED, or DISPUTED. Conflicting evidence and conflicting uses of a claim ID trigger review. Supplied context stays an inference until supported claim-level evidence exists. Competitor metadata establishes an observation of framing, not the truth of its factual claims. The fictional fixtures use `example.invalid` and must not be treated as real sources.

## Readiness and report categories

Every `IdeaCandidate` has `production_ready`, independent of `idea_score`. It defaults false and can become true only when evidence passes the configured threshold, required research is empty, similarity is CLEAR, and no factual/originality/context review flags remain. A high score is insufficient.

The deterministic generator always adds a specific research task for the new direction (for example, verifying an original practical test). Therefore its V1 output remains non-production-ready until the added work is actually resolved; no CLI switch bypasses that gate. The readiness function supports a later, reviewed provider/result without changing the model. Module 3 below consumes these immutable ideas and resolves research requirements before attempting a script.

The report separates:

- **RECOMMENDED FOR RESEARCH**: score at least 65, no duplicate/originality/factual review block, but research remains.
- **READY FOR SCRIPTING**: every readiness condition is satisfied, regardless of numerical score.
- **BACKLOG**: lower-priority or stale opportunities.
- **REJECTED / REVIEW REQUIRED**: near-duplicates, unresolved originality review, disputed facts, or insufficient context to assess originality.

All metadata-only briefs and ideas carry `CONTEXT_LIMITED`; they cannot become ready. Unknown fields are null with reasons. Unverified material claims, any outstanding research, or EvidenceQuality below 60 produce RESEARCH_REQUIRED. Disputed claims require factual review. No causation is inferred from competitor performance.

## Scoring and clustering

Configuration: `config/intelligence.json`. Component values and calculation rationale are persisted, not just totals.

```text
score = .22 DemandSignal + .15 Freshness + .15 Originality + .15 AudienceFit
      + .10 ProductionFit + .10 EvidenceQuality + .08 Expandability
      + .05 (100 - SaturationRisk)
```

Weights must cover all eight components, be finite/nonnegative, and sum to one.

- DemandSignal = 50% Radar strength +30% channel breadth +20% recency. Strength = `100*min(log2(1+median_adjusted_score)/log2(9),1)`; breadth for 1/2/3/4+ channels =25/60/80/100; recency=`100*2^(-median_source_age_days/30)`.
- Freshness: news=`100*2^(-event_age_days/14)`; evergreen=80; unknown=40. Publication date is a disclosed fallback capped at 60. A verified claim must explicitly support `event_date` via `supports_event_date` before that date is used. News older than 30 days is flagged stale.
- Originality=`100-maximum_similarity`; below 40 or similarity REJECT blocks the idea.
- AudienceFit: configured primary niche match=100; adjacent=60; unknown=30; explicitly unrelated=0.
- ProductionFit: five stated planning assumptions worth 20 each (single question, single mechanism/example, ≤3 material claims, feasible diagrams/screens, no bespoke footage). These are production assumptions, not feasibility proof.
- EvidenceQuality: equal-weight mean over distinct material claims; VERIFIED=100, PARTIALLY_VERIFIED=50, UNVERIFIED/DISPUTED=0. No assessable claims=0. This rates underlying claims; outstanding idea-specific research separately blocks readiness.
- Expandability: four proposed follow-up sections worth 25 each (mechanism, comparison, application, limitations/history). This measures available planned directions, not proven long-form demand.
- SaturationRisk=`100*dominant_angle_share*min((distinct_channels-1)/3,1)`; unavailable angle data=50 with uncertainty noted.

Trend clustering requires explicit event identity or exact normalized product/version plus event type, and every news member must fit the 14-day publication window with every other member. Evergreen clustering uses subject plus mechanism question. Broad topic labels and context-limited briefs stay separate. Entity aliases are configurable. Channel breadth takes precedence in trend ordering, but does not prove independent reporting. Unobserved angles are gaps only in the selected sample.

Originality combines character similarity, content-word trigram overlap, and structured premise equivalence. Thresholds: <55 CLEAR; 55–79.99 REVIEW; ≥80 REJECT. Exact duplicate generated directions in the same trend are consolidated; superseded ideas remain in history with `duplicate_of`, and their sources join the canonical idea. The checker is template-aware when comparing generated ideas: common scaffold text across genuinely different subjects is not automatically plagiarism. Exact duplicate text still triggers rejection. Competitor titles/context summaries are never exempted. CLEAR is not a certificate of originality or an embedding-based semantic judgment.

## Provenance, migration, and outputs

Schema version 2 is installed transactionally. Before migrating a version-1 database, Radar creates `<database>.pre-v2.bak`; rollback and idempotence are tested. Newer unsupported schema versions are rejected without changing them. Legacy Radar rows receive a nullable `created_at`; no timestamp is invented. Future Radar runs store creation timestamps and individual topic labels with classifier configuration hashes. Legacy topic assignments are recovered only from that run's saved groups; missing assignments are not silently reclassified.

New tables: intelligence_runs, intelligence_candidates, transcripts, evidence_sources, story_briefs, trend_clusters, trend_cluster_videos, idea_candidates, idea_sources, idea_scores. Intelligence references historical Radar IDs as provenance, rather than using cascading foreign keys that would silently erase Intelligence receipts when Radar expires. New runs append; they do not overwrite previous briefs, context, or ideas. Every candidate stores the selected source snapshot hash. Every idea embeds its relevant StoryBrief context and evidence references for future consumers.

Outputs:

```text
reports/intelligence/ideas.csv
reports/intelligence/ideas.json
reports/intelligence/trend_clusters.json
reports/intelligence/story_briefs.json
reports/intelligence/intelligence.md
reports/intelligence/runs/<intelligence_run_id>/<same five files>
```

JSON envelopes contain schema/scoring versions, run IDs, generation timestamp, provider versions, configuration/hash, source Radar metadata, and partial failures. Per-idea component scores and production readiness are explicit. The CSV includes accepted and rejected ideas, with status, source IDs, research tasks, components, and provenance. Markdown distinguishes categories, trends, source evidence, and uncertainties. Top-level files are latest views; run directories are immutable. Individual files use atomic replacement, not a transactional five-file bundle. A failed export leaves the already-persisted database run available. Concurrent writers to the same report directory are unsupported.

Retention is independent of immutability: after 30 days from source observation, non-synthetic Intelligence payloads expire while minimal run-ID/date receipts remain. Expired generated report bundles in the currently selected output directory are removed on an Intelligence invocation. Radar pruning also expires dependent Intelligence database payloads. Other output directories, copied reports, and pre-migration backups need manual cleanup by the applicable deadline. The CLI does not schedule background cleanup. Policy uncertainty documented for Radar remains applicable; this module introduces no policy permission gate or hidden network collection.

## Module 2 limitations

A deterministic system cannot fully understand arbitrary titles/transcripts, infer event dates safely, or certify semantic originality. With no supplied context, useful output may be sparse or entirely review-required. Templates can be generic and repetitive; shared scaffolding is explicitly distinguished from copied competitor language. Future semantic providers fit the existing interfaces but are not implemented. Source verification is a human-supplied assessment, not automated truth detection. All generation/scoring is reproducible for fixed source data, configuration, and analysis clock; run UUIDs and current-time freshness naturally vary across real runs.

## Module 3 — Research + Script Engine

Module 3 consumes one exact Module 2 idea snapshot, its embedded StoryBriefs, source snapshots and trend. It commits a research packet **before** angle refinement, outline, hooks or script generation. It does not generate media, retrieve transcripts, publish or schedule anything. The existing Module 2 `ResearchProvider` and `TranscriptProvider` interfaces remain unchanged; Module 3 has its own narrow interfaces for live evidence collection.

Separate protocols: `ResearchProvider` (search/fetch), `ResearchPlanner`, `ResearchSynthesizer`, `ScriptGenerator` (angle/outline/draft), `ScriptFactChecker`, `ScriptQualityReviewer`. The pipeline accepts any implementations. Live model/provider names exist only in configuration and provider setup. No agent framework or OpenAI SDK is required; the live adapter uses HTTPS Responses requests and bounded public HTML/text document retrieval.

### Offline validation (no key, no network)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -v
python main.py script --offline --research-file fixtures/scripts/sufficient_research.json
python main.py script --offline --research-file fixtures/scripts/contradictory_research.json
```

Fixtures are explicitly fictional. They seed a complete minimal Module 2 snapshot in `data/scripts-demo.sqlite3`, never the normal production database. Default reports go to `reports/scripts-demo/<script_id>/` and `latest.md`. The sufficient fixture is a hand-authored Nacre desktop search story, not a real product. The offline checker compares actual output text against an independent approved-text oracle and also runs the same deterministic traceability checks. Offline editorial scores are human-authored fixture inputs, not measured audience performance. It is not a general offline language model.

### First live test — user initiated, exactly one idea

Keep your existing `.env`; add these values without committing the file:

```dotenv
OPENAI_API_KEY=your_openai_api_key
MODEL_PROVIDER=openai
MODEL_NAME=gpt-5.6-terra
RESEARCH_PROVIDER=openai_web
MAX_SEARCH_CALLS=4
MAX_SOURCES=6
MAX_MODEL_COST_USD=1.00
MAX_RESEARCH_SECONDS=300
```

`YOUTUBE_API_KEY` is not needed to script an already stored Intelligence idea. The OpenAI project needs model and hosted-search access and available billing. No request is made by migration, import, tests, or offline execution. This implementation has **not** been validated against a paid live request. Run this only when you explicitly want that first test:

```bash
source .venv/bin/activate
python main.py script --top 1 --intelligence-run-id b4628fad-00e4-4234-bddc-b5c31f3171ef
```

That pinned run contains real YouTube leads, although Module 2 calls its metadata-only processing mode `offline`. It may legitimately end `RESEARCH_REQUIRED` or `REJECTED`. If source observations have expired, refresh Radar and Intelligence and select the new run; the CLI never silently substitutes another run. To use the latest complete nonsynthetic Intelligence run instead: `python main.py script --top 1`. Other switches: `--idea-id`, `--intelligence-run-id`, `--config`, `--db`, `--reports-dir`, `--offline --research-file`, and `--refresh-research`. Selection is printed before model calls. `--top` enables failure-isolated batches, but the first milestone remains one idea.

### Bounds and source handling

`config/script.json` holds provider configuration, pricing, research limits, word/duration limits, quality threshold and retry settings. The four uppercase limit environment variables override their lowercase JSON equivalents. Research ends early when the canonical story is resolved, critical claims have sufficient support, freshness is established, all requirements are resolved with claim references, and no material questions remain. The default maxima are four logical hosted searches, six successfully fetched sources and 300 research seconds. Generation uses the same total dollar budget. At most one editorial revision is attempted. A transport failure with uncertain billing stops further paid calls; only an explicit HTTP 429 may get one bounded retry. Refusals and incomplete responses are not blindly retried.

`source_priority = .50 authority + .30 relevance + .20 freshness` is a retrieval-order heuristic only. Unknown search results start with equal conservative scores. A direct primary record can establish its own product behavior without two sources or a high numeric rank. Synthesis records a **claim-relative** authority assessment and exact quote. Missing/fabricated quotes cannot support claims. Original documents, scope, attribution, dates and contrary evidence matter; competitor titles and search snippets do not constitute verification. Exact and near-duplicate document text, or a shared syndication identity, count as one independent source. This is a heuristic, not perfect syndication detection.

Only public HTTPS HTML/text pages are fetched, with size and time bounds. DNS is validated and pinned to a public address with TLS hostname verification; redirects, private addresses, unsupported documents, and failed URLs are skipped. No browser/login/paywall bypass or transcript scraping. JavaScript-only pages and PDFs are currently unsupported. Page dates/publisher names are source assertions; missing or ambiguous dates can prevent freshness approval. Source contents are treated as untrusted data in every model instruction. Prompt isolation and exact-quote checks reduce risk but do not eliminate model error or prompt injection.

### Evidence and readiness

Research claims reset prior verification and store status, materiality, type, supported wording, limitations, attribution requirement, supporting/contradicting sources and exact evidence passages. Passage IDs are stable hashes. A partial claim must have explicit limitations; scripts must preserve its supported scope. Packets include source records, independent-source count, freshness, requirement resolutions, and original provenance.

The generator refines an explicit angle and stores both original/refined versions, then makes an outline and five hooks. Hook scoring: Clarity 20%, Specificity 15%, Curiosity 15%, Stakes 10%, Novelty 10%, FactualSafety 20%, Brevity 10%. Missing mappings, hype phrases or factual safety below 90 make a hook ineligible. Ties use hook ID. All five hooks receive independent checking; these scores are editorial judgments, never viral probabilities.

Every script sentence is checked, even one labeled opinion by the generator. Material sentences require claim/source/passage mappings. The working title maps to claims. Factual visual/on-screen wording must be part of mapped script sentences; visual notes are production directions, and the semantic checker is instructed to inspect them too. The selected hook becomes a mapped sentence. Deterministic checks reject missing IDs, absent passages, unsupported numbers and missing required attribution; a **separate model call** then has to confirm semantic support for every sentence, all five hooks and title. A citation alone never implies truth. The same configured model is used, but checker prompts/calls are separate from generation; their errors can still correlate.

Quality weights: HookStrength 15%, Clarity 20%, NarrativeFlow 15%, InformationDensity 10%, Originality 15%, AudienceFit 10%, PayoffStrength 10%, ProductionFeasibility 5%. `spoken_naturalness` is an additional diagnostic, with model review plus deterministic flags for long sentences, awkward transitions, repetitive openings, jargon, delayed payoff, generic phrases, superlatives and robotic CTAs. Any unresolved flag sends the script to editorial review; it adds no new score dimension.

`READY_FOR_PRODUCTION` requires sufficient research, resolved requirements, a fact-check PASS, CLEAR originality in angle and quality review, quality ≥75, no spoken/editorial warnings, 110–150 words and estimated 45–60 seconds at 150 words/minute. PASS_WITH_MINOR_EDITS is **not** accepted automatically: revise and recheck. Contradicted core stories or originality rejection become `REJECTED`; incomplete/failed evidence becomes `RESEARCH_REQUIRED`; editorial issues become `EDITORIAL_REVIEW`. `REVIEW_REQUIRED` is an issue flag rather than a fifth top-level status. Readiness is not publishing approval. Originality limited to competitor metadata can remain REVIEW.

### Persistence, exports and costs

Migration 003 transactionally upgrades version 2 to 3 and creates `<database>.pre-v3.bak` before changes. Existing Radar/Intelligence rows are preserved. Tables: research_runs_v3, research_sources, research_claims, research_claim_evidence, research_packets, script_runs, script_hooks, script_drafts, script_claim_map, script_fact_checks, script_quality_reviews, script_cost_records. JSON payloads keep interface records compact; run IDs, timestamps, configuration hashes and provenance are SQL columns. Draft revisions are insert-only, with an SQL update guard. Retention deletes are allowed.

Reports contain idea.json, research_plan.json, research_packet.json, sources.json, claims.json, angle.json, outline.json, hooks.json, script.json, script.md, fact_check.json, quality_review.json, readiness.json, costs.json, research_outcome.json, failures.json, and revision snapshots. A failed research run writes null packet/draft artifacts, not a fabricated story. Complete fresh READY results are reused only for the same idea snapshot, exact Intelligence run and configuration hash; `--refresh-research` starts an explicit new run. Partial/failed runs are not reused. Reports are local exports; SQLite is the audit source. Concurrent report writers are unsupported.

Non-synthetic Module 3 payloads expire 30 days after the original source observation, preserving minimal run receipts. Any normal Radar/Script prune also expires Module 3 database payloads. Script invocations remove expired report bundles in the selected report directory. Other directories, copies and pre-migration backups require manual cleanup. No background retention task is installed.

Costs record returned model input/output tokens, estimated model/search dollars, actual HTTP fetch attempts/successes, logical search requests, and measured research/generation elapsed time. The research outcome separately records fixture/logical search iterations, so an offline source search never masquerades as a billed call. Unknown usage is `null`, not zero. Pricing defaults were checked against [the official model page](https://developers.openai.com/api/docs/models/gpt-5.6-terra) and [web search documentation](https://developers.openai.com/api/docs/guides/tools-web-search): $2/M input, $0.20/M cached input, $12/M output, $0.01/search as of 2026-09-20. The request-size cap remains below long-context pricing thresholds. Structured output follows [official documentation](https://developers.openai.com/api/docs/guides/structured-outputs).

When changing the model, configure all four verified pricing rates together in `.env`: MODEL_INPUT_USD_PER_MILLION, MODEL_CACHED_INPUT_USD_PER_MILLION, MODEL_OUTPUT_USD_PER_MILLION, SEARCH_USD_PER_CALL. Otherwise a model/pricing mismatch blocks paid requests. The dollar ceiling uses conservative input/output reservations and a hosted-search context reserve. It is an application estimate, **not a provider-enforced hard billing cap**: hidden search token volume and uncertain transport charges can exceed estimates. Reported overspend or unknown usage stops further calls. Use provider billing controls for an external spending limit.

This module was implemented from the approved architecture. It does not copy the reference repository's code or hook formula; the earlier reference attribution remains above. Tests cover the shared pipeline and mocked adapter contract, not live model access, real semantic accuracy, or the subjective strength of generated hooks. No paid request was made during implementation.

### Cheap story resolution and free selection preview

Before the full research plan runs, `StoryResolutionGate` asks only which exact real-world story the idea refers to. It uses the immutable idea, StoryBrief context, competitor references/channel and Radar metadata. It stores `story_resolution.json` and the same result in the existing research run's plan/outcome JSON; schema remains version 3.

```bash
python main.py script --preview
python main.py script --offline --research-file fixtures/scripts/unresolved_research.json
```

Preview opens SQLite read-only and requires neither `.env` nor any API key. It lists up to ten eligible ideas (fewer when fewer exist), including titles, channels, audience questions, unresolved flags and a separate `researchability_score`. Existing `idea_score` and Module 2 snapshots remain unchanged. Candidates within seven idea-score points compete on researchability: specific subject 25, named context identifiers 25, identifiable event 25, multiple competitor videos 10, context confidence up to 10, and absence of context-limited flags 5. A possessive person-name pattern in a title earns only a five-point hint when context identifiers are missing; it never establishes a real story. These deterministic heuristics can miss names or misclassify wording. Selection prints its reason; `--idea-id` still pins the user's exact choice.

Live preflight uses **one model request with one hosted web-search tool call**, no retries, at most two unique fetch attempts, a $0.08 estimated allocation and a 45-second research deadline. It uses the same configured model, with a 1,200-token output limit rather than full-packet synthesis. These preflight resources count toward the existing total research/cost limits. Lower preflight caps can be set with `preflight_max_cost_usd` and `preflight_max_seconds` in `config/script.json`; higher caps are rejected. As with the existing budget, reservations are estimates and reported overages/unknown usage stop further work; this is not a provider-enforced invoice ceiling. Time checks surround calls and network waits use remaining-budget timeouts.

The provider supplies `StoryResolutionResult`: canonical subject, named entities, alleged event, optional event date, product/company/person identifiers, resolvability score, ambiguity flags, narrow suggested queries, and independent source passages. `StoryResolver` is a separate optional protocol; `ResearchProvider` and `ResearchSynthesizer` remain separate. Only `RESOLVED` passes. It requires a specific subject/entity/event and an exact fetched passage assessed as credible evidence that the development exists. Competitor-only evidence, copied title passages, identified reposts, missing quotes, ambiguity and low confidence block entry. `PARTIALLY_RESOLVED` also stops with `RESEARCH_REQUIRED`. No full packet is fabricated. A preflight verdict is an identity check, not factual verification; the source-authority assessment is still fallible model judgment.

Preflight sources are reused in full research, with queries anchored to the resolved subject/event. Canonical URL identity drops fragments and query strings and normalizes host/trailing slash; `retrieved_url` retains the exact fetched address. This deliberately merges query-addressed variants conservatively and may merge genuinely distinct query-addressed documents rather than count them as independent support.

`source_topic_relevance` excludes off-topic documents before synthesis. It requires entity/product matches, overlap with the resolved event and, when both dates are known, proximity within 30 days. The default acceptance threshold is 70/100. This lexical filter is deliberately conservative: it can reject useful aliases or context sources, and it does not replace semantic fact checking. Full research stops on core contradiction, explicit entity/angle failure, two successive searches without new relevant evidence, or its normal resource limits. Off-topic pages and duplicate URLs cannot trigger additional syntheses. Full-research document attempts are also bounded by `max_sources` (including retained preflight documents).

Costs now include `story_resolution_cost`, `full_research_cost`, `script_generation_cost`, `fact_check_cost`, and `quality_review_cost`, retaining the old aggregate fields. Each executed stage tracks estimated model/search dollars, tokens, model/search/fetch counts and elapsed time. Unexecuted stages show zero; unknown billing is null in the affected stage. Existing historical cost records are not retroactively assigned invented stage costs.

Against the reported ~$0.47 unresolved first run, a rejection within the $0.08 preflight estimate avoids approximately **$0.39 (83%)**. That is a budget comparison, not a measured live saving. A resolved story proceeds into normal research and can cost more. The patch and regression tests make no paid live requests.

## Module 1 update — cohort-aware Market Radar

The version-2 watchlist has 20 explicitly identified channels in six market cohorts. `config/channels.json` stores display name, official API-resolved handle/ID, cohort, enabled flag, positive channel weight and `source_role`. NVIDIA and IBM Technology are `vendor_official`; ColdFusion and Asianometry are `media_explainer`; the remainder are `independent_creator`. Roles do not change opportunity scores. Cross-cohort reports separately count vendor and independent/media channels; vendor coverage must not be interpreted as independent audience corroboration.

```bash
python main.py research --resolve-channels
python main.py research --opportunities
python main.py research --cohort SECURITY_INFRA --opportunities
python main.py research --offline --opportunities
python main.py research --fixture tests/fixtures/market_radar.json
```

Resolution validates a requested handle through official `channels.list` and checks that the returned ID equals the configured ID. Display-name-only entries use official channel search to report alternatives but remain UNRESOLVED until an explicit handle/ID is chosen. Disabled channels make no requests. `--resolve-channels` writes `channel_resolution.json` and exits without collecting/scoring videos. No model, transcript, scraping, or Module 3 requests are involved.

The existing `cohort` column continues to mean **duration group** (`short_candidate` or `longer_video`). New `market_cohort` annotations identify AI_FRONTIER, DEV_SOFTWARE, SECURITY_INFRA, HARDWARE_CHIPS, TECH_BUSINESS and AI_TOOLS_SOFTWARE. Existing per-channel/duration median, ratio, velocity-adjusted score, percentile and eligibility calculations are unchanged. No global competitor median is introduced.

Collection precedence is explicit CLI override → channel override → cohort default. `--max-uploads` and `--lookback-days` therefore default to no override. The initial configuration has 15 channels at 100 uploads/90 days and five at 50 uploads/180 days (Dave2D, ColdFusion, Asianometry, Futurepedia, Matt Wolfe). `config/cohorts.json` holds these defaults and commercial-value labels. Collection retrieves up to the configured count; records outside the baseline window remain visible with their exclusion reason, never silently included in the median. Metadata reports actual date ranges, collection counts/caps and baseline sample sizes. The main market opportunity window is independently fixed by configuration at 30 days relative to analysis time. Offline replay does not make old uploads current.

Researchability is a conservative title heuristic configured in `config/radar_rules.json`: +35 named company/person/project (or uniquely identified CVE), +25 specific product/technology, +20 event, +20 version/CVE/generation, −20 hype, −20 unnamed/vague subject. Clamp to 0–100; no identifiable subject caps the score at 25. The default reporting threshold is 60. Entity/product alias dictionaries are separate to avoid awarding both categories for the same alias. Hints and reasons are stored; extraction does not establish truth or a verified canonical event. Product comparisons and ambiguous words can still create false matches; missing aliases create false negatives.

Cross-cohort groups require a specific identifier, product, or entity+event label, not generic AI. Only qualifying outliers within the current window contribute. Distinct cohorts C and channels N count once each. Let S be the median of each channel's median adjusted score and A the median age of each channel's newest supporting upload:

```
normalized_radar(S) = 100 * min(log2(1 + S) / log2(9), 1)
signal_strength = 100 * (
    .45 * min((C - 1) / 2, 1)
  + .20 * min((N - 1) / 3, 1)
  + .25 * normalized_radar(S) / 100
  + .10 * 2**(-A / 14)
)
```

A signal requires at least two market cohorts. All supporting video/channel/cohort IDs, independent/vendor channel counts, maxima, channel-balanced median, recency and formula components are persisted. This means subject overlap, not confirmation that videos describe the same event. A cohort-filtered run discloses its scope; it cannot establish evidence from uncollected cohorts.

For eligible current videos only:

```
opportunity_score = .55 * normalized_radar_signal
                  + .25 * researchability_score
                  + .20 * cross_cohort_support
```

Cross-cohort support is the maximum matching signal, never the sum. Adjusted Radar scores ≥8 reach the 100-point normalization ceiling. Under-24-hour, under-sample, unavailable and stale-for-current-view records keep NULL opportunity scores. Opportunity ordering is separate from unchanged Radar ranks. Every component is stored. Commercial-value labels and source roles do not multiply scores or predict views, CPM, RPM or revenue.

Cohort medians first compute each channel's median and then take the weighted median across channels (default weight 1), so a prolific channel does not receive extra weight. Raw video/outlier counts remain visible and are not ranking inputs. Top-five cohort lists take one opportunity per channel before a second round. Recurring subjects require multiple channels. Independent/media and vendor outliers and median scores are shown separately.

Production fit uses metadata only: testing/benchmarks/unboxing/hands-on reviews are POOR; personality-led opinions/reactions and insufficient context are MEDIUM; identifiable software/product releases, security, architecture, comparison, research and business events generally receive GOOD. Harder-production rules take precedence. Nothing is rejected automatically on this tag.

New reports: `cohorts.md`, `opportunities.csv`, `opportunities.json`; existing reports remain. Every new bundle is also saved under `reports/runs/<run_id>/`. New runs include competitor/cohort/scoring versions and complete configuration snapshots/hashes. CSV titles are escaped against spreadsheet formula injection.

Migration 004 upgrades schema 3→4 transactionally, first creating `<database>.pre-v4.bak`. It adds radar_market_runs, radar_opportunities, radar_cohort_summaries and radar_cross_cohort_signals. It does not backfill or reclassify old results. **Historical preservation now supersedes the earlier Radar auto-pruning description:** Radar invocations expire cache entries only; saved Radar runs, scores and source records are no longer automatically deleted by `Database.prune`. Module 2/3 payload expiry still applies when their existing cleanup paths run. No Module 3 implementation was changed. Preserving historical API-derived data is not a claim of policy permission; the previously documented policy/retention uncertainty remains an operator responsibility.

An uncached 20-channel run at these caps is approximately 20 channel lookups +35 playlist pages +35 video batches =90 general quota units, before retries. Cached lookups/pages lower usage. Current official quota documentation separates search calls into their own quota bucket; request accounting reports `quota_units_estimated_used` for general endpoints and `search_quota_units_estimated_used` separately. This watchlist normally needs no search calls once IDs/handles are pinned. Account-wide usage must be read from the Google Cloud console; CLI figures count this invocation's attempted requests conservatively.


### Module 3 source selection and conservative billing

Source ranking and preflight now share domain ownership classification. Exact
product/release/docs matches outrank generic first-party pages; community posts and
unproven CDN documents do not become official documentation. Per-result components,
canonical groups, rejection reasons and content/URL mismatch flags are exported in
`research_searches.json`. Weights are configurable in `config/script.json`.

Live requests require Node.js (20+ recommended, configurable as `tokenizer_node`)
for offline token counting with the bundled `o200k_base` vocabulary. Nothing is
fetched to initialize the tokenizer. The selected encoding counts local serialized
request text; server framing/model encoding may differ, so reservations also include
a conservative byte-bound allowance, protocol margin and hosted-search allowance.
An unavailable tokenizer blocks dispatch.

Every attempt reserves full non-cached input/output rates before dispatch. Unknown
billing retains the entire reservation instead of setting spend to null. The numeric
upper bound includes known spend, retained unknown charges and active reservations.
One retry is allowed only for safe read-only/generation transport failures when a
second full reservation and sufficient time fit. Usage reconciliation releases the
unused reserve; historical unknown charges are never assumed free. Cost/time limits,
factual evidence gates, and the overall research pipeline remain unchanged.

See `tech_uncovered/scripting/SOURCE_SELECTION_COSTS.md` for scoring and ledger details.

### Exact evidence links and editorial pivots

Research now stores exact fetched-text offsets and claim links in each passage,
plus `evidence_passages.json`. Existing source IDs remain `evidence_ids`; passage
IDs remain compatible with sentence and hook mappings. SQLite's existing JSON
payloads and `research_claim_evidence` joins store these additive fields without
a schema migration.

A deterministic missing-link repair recognizes a limited set of explicitly
labelled documentation tables: API-scoped tool support, modalities, fine-tuning,
context/output limits and base token prices. It requires a fetched first-party
model page matching the canonical subject and a claim-relative primary-source
assessment. It does not use authority scores as proof. Repairs preserve
`original_supported_wording`, generate exact attributed documentation observations,
and set `verification_scope=SUPPORTED_WORDING_ONLY`. Broader original statements,
launch dates, independent performance, and comparison claims are not verified by
this repair. Unrecognized layouts/prose remain unresolved; this is not a general
semantic entailment engine. Existing supplied quotations still require the
synthesizer's claim-relative assessment and downstream independent fact checking.

Requirements resolve independently. `ANGLE_UNSUPPORTED` no longer erases partial
research. After exhaustive comparison discovery, at least three verified material
documentation claims and grounded identity may yield `angle_pivot.json` with
`ANGLE_PIVOT_RECOMMENDED`. Its topics are derived from extracted evidence, never
from a model's free-form safe-angle suggestion. This recommendation leaves the
original comparison blocked and does not trigger script generation.

Freshness assessments distinguish `NEWS_FRESHNESS`, `PRODUCT_CURRENTNESS`, and
`EVERGREEN`. News remains the default. An explicitly scoped research plan may set
`freshness_requirement.mode` to either documentation mode; this does not remove
outstanding launch or comparison requirements. Documentation modes use recent
retrieval time, not a fabricated publication date. They describe saved observations,
not a guarantee that a vendor page remains unchanged. A pivot requires explicit
editorial acceptance and a new appropriately scoped plan before scripting.

Offline replay (no provider instantiation, no database changes, no paid calls):

```sh
.venv/bin/python tools/replay_evidence_links.py \
  reports/scripts/script-ef63586e-e6f8-488e-9f19-56f174e12566 \
  --output reports/evidence-linking-replay
```

The replay preserves the original artifacts, records their SHA-256 hashes, and
exports before/after statuses, exact evidence and the proposed pivot. Saved live
artifacts are required for this command; regression tests use fictional evidence.

### Explicit editorial pivot acceptance

Accept one compatible saved pivot by idea ID. This path does not instantiate a
research provider: story resolution, discovery, fetching and synthesis are skipped.
It verifies the original run lineage, reproduces the repaired claims/pivot from
saved sources, checks evidence age, and (in live mode) checks the original packet,
source and selection snapshots against SQLite. An explicit folder can be selected
with `--pivot-dir`; otherwise the latest compatible saved artifact is selected.

Offline acceptance rehearsal, using the existing saved evidence:

```sh
python main.py script --idea-id idea-6c0ebae5c96c3cf3 --accept-pivot \
  --offline --dry-run --pivot-dir reports/evidence-linking-replay
```

This writes `reports/pivot-acceptance-dry-run/pivot_acceptance.json`, an accepted
scope packet and `dry_run.json`. It makes no model calls, writes no database rows,
and does not fabricate a script or a production-readiness verdict.

Only when explicitly ready to spend on generation/review:

```sh
python main.py script --idea-id idea-6c0ebae5c96c3cf3 --accept-pivot
```

Live acceptance creates a new run and packet; the original unsupported comparison
remains unchanged. `pivot_acceptance.json` and SQLite record accepted scope,
verified/partially verified claim IDs, forbidden claims, source-run lineage and
artifact hashes. Identity is limited to documented existence, excluding vendor
superlatives. No additional source facts become authorized merely because they
appear elsewhere on the saved page.

Generation shares the existing angle → outline → five hooks/script → independent
fact-check → quality-review flow. Deterministic scope/mapping checks plus the
independent semantic checker block new claims, launch framing and unsupported
comparisons. Fact-check failure stops the accepted-pivot path before editorial
review. All existing word, duration, hook and quality thresholds are unchanged.
A refusal pattern is only an extra check, not a substitute for semantic review.

There are five initial model requests; one editorial revision adds three. Transport
retries can double attempts, but each requires another affordable reservation.
The dry-run ceiling uses the configured 180KB request bound and full output limit;
the existing total application budget remains authoritative and can stop an
otherwise valid run. Dry-run safety does not confirm credentials, model availability,
future model output quality or guaranteed completion within the budget.

### Auditable pivot generation and compact prompts

Accepted-pivot model requests use `PivotEvidenceBundle`: canonical subject,
accepted angle, authorized claim statuses/wording/limitations, source IDs and
short exact passages, forbidden categories and format requirements. Full source
pages, Radar payloads, failed research narratives and competitor metadata are
excluded. Originality review must therefore acknowledge absent competitor
execution context rather than assume CLEAR. Research and accepted scopes are
unchanged.

Angle candidates use `scope_contract_version=2` and explicit propositions with
`text`, `factual`, `claim_ids`, `evidence_ids`, `passage_ids` and `surface`.
Angle/payoff proposition coverage is checked against generated surface text;
this is not an exact wording comparison against evidence. Supported wording may
be paraphrased within bounded documentation grammars, including numerical unit
equivalence. Unknown wording fails closed for editorial review; missing or
unauthorized factual evidence requires research. Non-factual editorial framing
has no evidence-match requirement, but a factual assertion cannot escape checks
by being labelled editorial. Forbidden categories remain blocking.

The deterministic validator supports API-scoped computer-use support, fine-tuning
restrictions, modality restrictions, context/output limits and base pricing.
It is not a general entailment model: unrecognized paraphrases may need editorial
rephrasing. Independent fact checking remains mandatory. Older fixture/provider
contracts retain their existing gates; new live pivot requests use version 2.
No additional semantic-model requests or automatic wording retries were added.

Raw candidates are committed to SQLite **before** validation/normalization, then
exported as `angle_candidate.json`, `outline_candidate.json`,
`hooks_candidate.json`, and `script_candidate.json`, with numbered copies for
revisions. A validator crash leaves the raw candidate with PENDING validation.
`scope_validation.json` records the latest scope decision; `scope_validations.json`
retains all decisions and exact rejected spans. `generation_metrics.json` and
cost attempts record local input tokens, payload bytes, evidence-bundle tokens
and historical-context tokens. Existing JSON storage needs no migration.

Offline inspection of the failed live run, without reconstructing missing output:

```sh
.venv/bin/python tools/replay_pivot_scope.py \
  reports/scripts/script-c6bea42e-011f-4be3-b92c-ca61f70947e4 \
  --output reports/pivot-scope-replay
```

The old run retained usage and a response ID but no successful response body.
Its exact offending proposition and whether it would pass the new validator
cannot be recovered from those records. The replay does not fetch that response.

#### Editorial framing, polarity and composite scope

The scope validator now branches on editorial intent before demanding evidence
mappings. Bounded guide/checklist language is editorial; a disguised statement
such as “the model costs $10” remains factual even when labelled `factual=false`.
Cautions such as “do not treat listed support as evidence of reliability” are
recognized at clause scope. A separate positive assertion remains blocked; a
negative performance judgment is not automatically treated as a caution.

Category-list propositions are decomposed into atomic units. Each unit must be
covered by an authorized claim and its explicitly cited structured passages.
The union can support `SUPPORTED_COMPOSITE_PARAPHRASE`; unsupported evaluative
adjectives do not inherit support from adjacent units. Validation reports persist
`atomic_units`, exact failing units, and per-concept `polarity_analysis`.

For version-2 angles, the executor derives its internal `evidence_basis` IDs from
successfully validated factual proposition mappings. A prose-only summary in that
legacy field cannot override those mappings. The raw candidate remains unchanged.
Research, prompt compaction, accepted scopes and production gates are unchanged.

Replay the exact saved candidate without model calls:

```sh
.venv/bin/python tools/replay_composite_scope.py \
  reports/scripts/script-15b9ca74-a226-4ac2-90a4-6a7b6f9229fa \
  --output reports/composite-scope-replay
```

This writes a new validation report and an execution-ready angle copy, verifies
that original artifacts remain byte-for-byte unchanged, and reports whether the
angle can reach outline generation. It does not generate an outline or script.

### Resume a persisted angle-stage run

```sh
python main.py script --resume script-15b9ca74-a226-4ac2-90a4-6a7b6f9229fa
```

This minimal resume supports accepted-pivot runs stopped before outline generation.
It loads the saved candidate, verifies packet/selection/candidate provenance against
SQLite, checks evidence age, and requires current scope validation to return
PASS / CONTINUE before creating a model client. Failure stops without a model call.

The validated candidate is promoted to the original run's `angle.json`. Original
candidate, audit, cost and readiness artifacts remain unchanged. New work is saved
under a new script-run directory and ID, with the original source research-run ID,
accepted scope, selection snapshot and reused run lineage preserved. The new
`resume_metadata.json` records `resumed_from_script_id`, `resumed_at`,
`stages_reused`, and attempted `stages_executed`; the same metadata is stored in
SQLite, including checkpoints before new stages.

Outline generation is the first new model request. Story resolution, discovery,
fetching, research synthesis and angle refinement are skipped. A fresh cost ledger
and the configured budget cover only new generation/review work; prior cost records
are neither overwritten nor counted again. Existing factual/editorial gates and
bounded revisions remain active. `--reports-dir` selects the script reports root;
`--db` selects its matching database. Resume cannot be combined with research or
idea-selection flags. No live resume is performed merely by installing this change.

### Cohort-aware intake and story-first preview

M2 now defaults to **30 current scored Radar opportunities** (`intake_limit` in
`config/intelligence.json`; override with `intelligence --top N`). It preserves
existing quality ordering and Radar scores. The coverage floor is the global
Nth opportunity score minus `intake_quality_band` (default 7). First select the
strongest non-POOR opportunity per cohort inside that band, then fill globally.
Weak cohorts are not forced into coverage. POOR-fit items retain their original
last-place priority for global fill. Every selected snapshot records
`selection_phase`, `selection_reason`, `cohort_rank`, and `global_rank`; its original
Radar snapshot hash remains unchanged.

`script --preview` defaults to **RECOMMENDED FOR RESEARCH + READY FOR SCRIPTING**.
Use `--include-backlog` to explicitly include visibly labelled BACKLOG leads.
Rejected, review-required, duplicate and similarity-review items remain excluded,
even with that option. This eligibility policy also applies to script selection;
explicitly requesting an idea does not bypass it.

Preview first selects the best eligible angle per canonical story, then fills with
second angles, with a hard maximum of two per story. Best-angle selection retains
the bounded researchability tie-break: within seven idea-score points, prefer
higher preview researchability. Between stories, an unrepresented source cohort
wins within that band before researchability; no score bonus is added. Fewer than
ten results is valid. Source-cohort diversity is not evidence of subject diversity.
Canonical story IDs derive from the existing subject/event/time-window cluster,
not raw topic text. IDs are local to that cluster snapshot; expanding its source
membership can change its ID in a subsequent M2 run.

Researchability is an explicitly versioned pair:

- `m2_researchability_score` / `radar-context-v1`: Radar/context heuristic used by
  M2 recommendation gates (legacy field `idea_researchability_score` is retained).
- `preview_researchability_score` / `context-resolvability-v1`: context identity,
  event and confidence heuristic for bounded selection tie-breaking. It does not
  override M2 eligibility or represent verified evidence.

New M2 JSON payloads persist story identity, angle type, both researchability values,
and default-preview rank/phase metadata. Existing runs are not rewritten; read-only
preview derives the same fields from their retained snapshots. Optional backlog
preview ranks are computed for that request. Existing JSON payload storage requires
no SQL migration. All Radar/idea score weights and readiness gates are unchanged.

Offline replay (read-only production database, disposable replay database; no API):

```sh
python tools/replay_diversity.py --db data/intelligence.sqlite3 \
  --run-id 21c10e47-c54a-40c7-8452-f23913c8ed3b
python main.py script --preview
python main.py script --preview --include-backlog
```

Replay compares 20/30/40/50 inputs and old/new intake and preview independently.
Its report is `reports/diversity-replay/replay.md`; it does not install a new latest
production M2 run. To create a new offline M2 run from retained Radar data explicitly:

```sh
python main.py intelligence --offline --run-id 08fa34b9-4afd-437a-b5a2-784687ce5d3c
```

### Deterministic metadata subject resolution

M2's `MetadataSubjectResolver` runs before metadata-only idea generation. It uses
explicit title entities, conservative aliases, product/version/CVE patterns and
broad event language. A developer cohort can disambiguate “engineer”; an official
channel can identify a source owner, but neither automatically supplies a story
subject. V1 does not consume descriptions or retrieve additional context.

Each StoryBrief retains `metadata_subject_resolution`, including canonical subject,
subject type, named entities, product/project identifiers, versions, title temporal
markers, event/change, extraction method, unresolved reasons and HIGH/MEDIUM/LOW
**extraction** confidence. Identifier/version/temporal fields are lists. This is
separate from factual confidence: metadata remains CONTEXT_LIMITED, title events
remain allegations and no claim becomes verified. Publication dates are not
converted into event dates.

The resolver distinguishes:

- `CONCRETE_STORY` / `EVENT_STORY`: title identifies a subject and a broad event.
  Event templates investigate mechanisms, implications and examples; comparison
  requires explicit comparison context. No case, device model, outcome or target
  is invented to complete a story.
- `EVERGREEN_TOPIC`: explicit educational/technical topic, with explanation,
  practical-lesson, misconception-investigation and mechanism templates. No
  launch, study, “what changed” or manufactured “why now” is added.
- `INSUFFICIENT_CONTEXT`: no ideas generated, even if a company name is recognized.
  Anonymous financial anecdotes, vague reactions and multi-news roundups remain
  blocked until their scope can be established.

Clustering retains version/event/time-window distinctions. Evergreen product
explanations can group despite optional company labels, while educational topics
remain separate from concrete event stories. Thus one product may legitimately
have separate evergreen and event story IDs; the existing preview cap is per
story ID, not per product name.

Researchability formulas, Radar opportunity scores, idea-score weights, intake
and preview policies are unchanged. Improved fields can change scores naturally;
original Radar snapshots and researchability values remain available. A usable
subject does not automatically meet the recommendation threshold.

Replay the exact retained 30-input baseline without updating production history:

```sh
python tools/replay_subject_resolution.py --db data/intelligence.sqlite3 \
  --baseline reports/diversity-replay/new-intelligence.json
```

The replay asserts identical input snapshots and order, uses a disposable database,
and writes `reports/subject-resolution-replay/replay.md` plus before/after JSON.
The saved `before-intelligence.json` in that directory is an immutable baseline
copy for future reruns if the diversity replay is regenerated.

### M2 → M3 entry contract

New M2 idea snapshots persist `subject_type`, `story_requirement`,
`story_requirement_satisfied`, `story_resolution_mode`, `m3_entry_ready`,
`m3_entry_blockers` and `m3_entry_contract_version`. Requirements distinguish
EVENT_REQUIRED, EVENT_OPTIONAL, EVERGREEN_OK and COMPARISON_CONTEXT_REQUIRED.
Comparisons require explicitly supplied `comparison_context.subjects` (at least
two distinct subjects) and `comparison_context.criterion`; neither is invented.

Company/person/event templates use business consequences, documented statements
or reported-event mechanisms rather than treating those entities as products.
Existing stored malformed text is blocked, not silently rewritten or rescored.
Unsatisfied story requirements prevent new RECOMMENDED FOR RESEARCH labels.

**Semantic satisfaction and executable M3 entry are separate.** An evergreen
product explanation can satisfy its M2 requirement without any event. Its mode is
EVERGREEN_SUBJECT. However, M3 currently has only an event-resolution gate; this
patch deliberately does not add an evergreen or comparison implementation.
EVERGREEN_SUBJECT and COMPARISON therefore carry
`STORY_RESOLUTION_MODE_NOT_SUPPORTED` and remain outside normal paid-entry preview.
EVENT, SECURITY_EVENT and BUSINESS_EVENT retain the existing event contract; these
labels do not add new M3 research behavior. No synthetic event is manufactured.

Default script preview recalculates the current contract on retained snapshots and
requires entry readiness in addition to editorial eligibility. `--include-backlog`
can expose blocked entries with visible reasons, but cannot bypass the live paid
entry guard. Entry-ready means only that the metadata contract can be attempted;
it does not establish that the subject/event exists, that evidence will be found,
or that the result is ready for production. Production readiness remains separate.

Read-only replay of the latest production M2 snapshot:

```sh
python tools/replay_entry_contract.py
python main.py script --preview
python main.py script --preview --include-backlog
```

The replay compares the prior and new eligibility predicates under the same
story-first selection rules, preserves all idea scores and writes
`reports/entry-contract-replay/replay.md`. Old snapshots are not migrated or
rewritten; fields are derived for preview and persisted in newly generated M2 runs.
The explicitly fictional Nacre test fixture includes its existing fictional
release context, so offline fixtures satisfy the same contract without a special
production bypass.
>>>>>>> 09773b8 (Initial Tech Uncovered automation pipeline)
