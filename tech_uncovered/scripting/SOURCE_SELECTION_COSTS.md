# Source selection and conservative billing

One shared authority classifier serves search ranking, fetched source metadata and
preflight resolution. Domain matching respects label boundaries; more specific
community/CDN rules override parent-domain rules. First-party ownership never
verifies a claim. Claim-relative assessments remain required, and cannot promote
community or unproven hosted documents into primary documentation.

The default retrieval score is:

`0.30 requirement_match + 0.30 entity_match + 0.20 authority + 0.15 document_type_fit + 0.05 freshness`

All components are 0–100. Unknown freshness is zero, not an invented date. Requirement
fit distinguishes launch, product, API, technical, educational, secondary, community,
and generic documents. Exact entities in URLs/titles/headings beat body-only mentions
(which may be navigation). Unrelated versioned pages/PDFs are rejected. Scores rank
retrieval, never truth. URL/content version disagreement subtracts 25 points and
flags CONTENT_URL_MISMATCH; such documents remain contextual evidence but are not
primary identity evidence. Canonical/tracking/localized variants share one group;
alternative URLs are retained for inspection. Distinct translated slugs cannot be
reliably collapsed without content equivalence, so remain separately identified.

The executor ranks all results before allocating fetch slots and retains every
component and decision in research_searches.json. Previously attempted canonical
URLs remain skipped. Full research does not repeatedly fetch a failed launch URL.

The local o200k counter counts serialized request text using a bundled vocabulary
and project-owned byte-pair merge code. Attribution is in assets/NOTICE.txt. It uses
Node's Unicode regex support; no tokenizer service, package install or vocabulary
download occurs. Encoding choice is explicit configuration, not proof of a future
model's server encoding. Ordinary text is counted without interpreting embedded
special-token strings as privileged tokens.

Reservation calculation uses full non-cached rates:

- locally counted input tokens;
- an encoding/framing safety allowance up to the serialized UTF-8 byte bound;
- the configured protocol margin (1024 tokens);
- hosted-search context allowance when applicable;
- maximum output tokens at full output rate, plus the expected search charge.

Each attempt records reserved_cost_usd, actual_cost_usd, released_reserve_usd, local
input count, payload size and status. The total upper bound is known cost plus all
retained unknown reservations plus in-flight reservations. A failed attempt releases
nothing. Retrying requires a separate full reservation; at most one retry is allowed.
Terminal/missing-usage errors do not erase prior known costs or poison later budget
checks. Reported usage exceeding a reservation is recorded honestly and stops work;
this application bound is not a provider-enforced billing cap.

The historical replay reconstructs the failed synthesis payload from saved artifacts.
No original wire payload or reservation receipt exists, so it is a counterfactual
budget decision, not recovered historical billing. Original artifacts are unchanged.
