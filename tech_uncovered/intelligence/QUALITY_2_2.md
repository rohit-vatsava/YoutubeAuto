# Intelligence 2.2

This patch only changes Module 2. Radar snapshots remain immutable. Additive
fields use existing JSON database payloads; no schema migration is needed.

Selection puts POOR production fits last, then sorts descending by the configured
`selection_order` (default opportunity_score, researchability_score,
velocity_adjusted_score). Entity/event presence breaks ties. Historical snapshots
without these fields retain velocity ranking. The top limit remains 20; it does
not guarantee that every example product is selected.

Structured hints seed title-anchored subjects. They are INFERENCE, never FACT.
Product/version and event keys allow metadata-only clustering within the existing
14-day window. Suspected roundups remain separate. Vendor and independent support
counts remain separate; neither verifies claims. Bare broad subjects generate no
ideas. Product naming and roundup detection are conservative heuristics and can
still miss or over-expand names.

Idea researchability = 50% of the strongest source researchability + 20 for a
non-broad subject + 5 per distinct entity (maximum 15) + 15 for an alleged event,
minus 25 for suspected roundups (otherwise 15 for more than four entities),
clamped to 0–100. This is a research prioritization heuristic, not evidence quality.
The configurable researchability_threshold defaults to 60. CLEAR similarity,
non-POOR production fit, non-stale/non-ambiguous context and no duplicate/review
rejection permit RECOMMENDED_FOR_RESEARCH. Legacy category strings are preserved;
the additive review_status uses underscores. Metadata-only ideas always retain
CONTEXT_LIMITED and required research, and cannot be production ready. CLEAR is a
lexical check, not certification of originality against unseen transcripts.

```
python main.py intelligence --offline --run-id 08fa34b9-4afd-437a-b5a2-784687ce5d3c
python main.py intelligence --preview-researchability --run-id 08fa34b9-4afd-437a-b5a2-784687ce5d3c
```

Preview reads the latest complete, non-expired persisted Intelligence run for the
specified Radar ID (or latest overall), using SQLite read-only mode. It does not
initialize providers, regenerate ideas, refresh Radar, or call network/model APIs.
Run ordinary offline Intelligence first to update an older preview.
