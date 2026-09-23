# Story identity versus full research

Preflight resolves identity, not factual claims. It now records stable URL-based
`resolution-source-*` IDs separately from Research SourceRecord IDs. Confirmed
tool discoveries can be DISCOVERED; retrieved page text is FETCHED; a supplied
passage matched against fetched text is VERIFIED_PASSAGE. This last state means
an exact passage was located, not that every claim it might be used for is true.

Never promote model-generated snippets/quotes to search-provider metadata. The
live adapter copies title, snippet and actual query only from tool results, or
stores null when unavailable. Unknown historical discovery provenance is explicitly
unconfirmed, with null acquisition_state. Its URL remains available for audit but
is not counted as credible. Successful historical fetches are independent provenance.

Resolution is deterministic: specific subject/entity/event, normalized confidence
at least resolution_score_threshold (default 70), one accepted non-competitor event
source, no contradictions or unresolved ambiguity. Fractional 0–1 confidence is
normalized to 0–100. Model status and descriptive source-type wording do not decide
the result. Specific subject with identity evidence but weak event/confidence is
PARTIALLY_RESOLVED. No identity evidence or a direct contradiction is UNRESOLVED.

Authority comes from `resolution_authorities` configuration (domain ownership),
not the model's OFFICIAL label. Domain/subdomain matching is boundary-aware.
String values name first-party owners and must match the story's company identity.
For reputable reporting, a value can be
`{"owner": "Publisher", "authority_type": "REPUTABLE_SECONDARY"}`.
Shared owners count once. Unknown/unconfigured domains fail closed; repositories
and papers on shared hosts need an appropriately scoped future authority resolver.
The built-in fictional provider uses explicitly marked fictional source metadata.

At most two unique sources are fetched in preflight. Known transient errors on
configured official domains get one retry if the time budget permits; permanent
errors do not. All attempts retain URL, error class and retry metadata. Fetch
failures do not erase discovery evidence. Full research now runs a material-requirement discovery queue before synthesis.
Previously failed URLs are not immediately retried; alternate official-source
searches seek fetchable evidence within the existing source/time budget. It receives fetched
SourceRecords only, never discovery snippets. Claim/passage, numeric/comparison,
freshness, fact-check and production-readiness gates are unchanged.

The replay helper `tech_uncovered.scripting.resolution_replay.replay` only reads
persisted files and returns a new decision. It makes no network/model calls and
never overwrites the original run. Preflight resolution is permission to investigate,
not permission to script or publish; alleged event dates and capabilities remain
unverified until full research establishes them.
